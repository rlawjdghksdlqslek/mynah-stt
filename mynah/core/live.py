"""Live chunk transcription worker and its hallucination guard.

Whisper falls into repetition loops on low-SNR audio — 12 of 28 transcripts
from this project's own meetings contained one, worst case "Crystal" x219,
which destroys the segment and makes the transcript useless as LLM input.

Gain normalization removed these in measurement, but the guard stays as an
independent second line of defense: mlx-whisper has no beam search
(NotImplementedError), and beam search was what suppressed these loops on the
CPU path. A chunk that loops is retried through WhisperX with beam_size=5.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from mynah.core import session as session_mod
from mynah.core.audio import normalize_gain
from mynah.core.format import format_timestamp

LOOP_UNIGRAM = 8    # same token repeated N times in a row
LOOP_NGRAM = 3      # same 6-gram repeated N times in a row
NGRAM_SIZE = 6
MIN_LOOP_SPAN = 12  # tokens the repeating region must cover
MAX_CONSECUTIVE_RETRIES = 3


def worst_repeat(tokens: list[str], n: int) -> int:
    """Longest run of the same n-gram repeated back to back."""
    if len(tokens) < n:
        return 0
    worst, i = 0, 0
    while i <= len(tokens) - n:
        gram = tokens[i:i + n]
        run, j = 1, i + n
        while tokens[j:j + n] == gram:
            run += 1
            j += n
        worst = max(worst, run)
        i = j if run > 1 else i + 1
    return worst


def has_loop(text: str) -> bool:
    """Is this text a hallucination loop rather than speech?"""
    tokens = text.split()
    if not tokens:
        return False
    if worst_repeat(tokens, 1) >= LOOP_UNIGRAM:
        return True
    # Check every phrase length up to NGRAM_SIZE, not just NGRAM_SIZE itself:
    # a short repeating phrase (e.g. a 4-word phrase repeated 4x) has no
    # aligned repeat at exactly n=6, but is exactly the loop this guards
    # against.
    #
    # Require the repeating region to be substantial, not just frequent.
    # Real hallucinations are long (Crystal x219; a 4-word phrase x4 = 16
    # tokens). Ordinary speech repeats short phrases briefly -- "조금 더" x3
    # is 6 tokens of real meeting audio, and flagging it deletes the whole
    # chunk.
    for n in range(2, NGRAM_SIZE + 1):
        run = worst_repeat(tokens, n)
        if run >= LOOP_NGRAM and run * n >= MIN_LOOP_SPAN:
            return True
    return False


def mark_gap(seconds_start: float, seconds_end: float) -> str:
    """Placeholder for a span that could not be transcribed cleanly.

    An explicit marker beats silently dropping audio: the reader (and the LLM
    downstream) can see that something is missing rather than assume the
    meeting simply went quiet.
    """
    return (
        f"[{format_timestamp(seconds_start)}-{format_timestamp(seconds_end)} "
        f"transcription failed: repetition loop]"
    )


def guard_segments(segments: list[dict]) -> list[dict]:
    """Replace hallucination-loop segments with a gap marker, in place.

    The live path guards per chunk. Whole-file transcription gets the same
    guard per returned segment, so one looping stretch costs that stretch
    rather than the file.
    """
    for seg in segments:
        if has_loop(seg.get("text", "")):
            seg["text"] = mark_gap(
                float(seg.get("start", 0.0)), float(seg.get("end", 0.0))
            )
    return segments


TAIL_CHARS = 120
BYTES_PER_SECOND = 32000


def _default_transcribe(pcm, *, model_name, language, initial_prompt, backend,
                        beam_size=None):
    from mynah.core.transcribe import transcribe_pcm  # lazy: heavy ML import
    return transcribe_pcm(
        pcm, model_name=model_name, language=language,
        initial_prompt=initial_prompt, backend=backend, beam_size=beam_size,
    )


def transcribe_chunk(
    pcm: bytes,
    *,
    start_seconds: float,
    model_name: str,
    language: str,
    prompt: str,
    backend: str,
    allow_retry: bool = True,
    transcribe_fn: Callable[..., dict] | None = None,
) -> dict[str, Any]:
    """Transcribe one chunk and return a meeting-relative segment."""
    fn = transcribe_fn or _default_transcribe
    end_seconds = start_seconds + len(pcm) / BYTES_PER_SECOND

    result = fn(
        normalize_gain(pcm), model_name=model_name, language=language,
        initial_prompt=prompt, backend=backend,
    )
    text = (result.get("text") or "").strip()
    retried = False

    if has_loop(text) and allow_retry:
        retried = True
        result = fn(
            normalize_gain(pcm), model_name=model_name, language=language,
            initial_prompt=prompt, backend="whisperx", beam_size=5,
        )
        text = (result.get("text") or "").strip()

    failed = has_loop(text)
    if failed:
        text = mark_gap(start_seconds, end_seconds)

    return {
        "start": start_seconds,
        "end": end_seconds,
        "text": text,
        "retried": retried,
        "failed": failed,
    }


def run_worker(
    session,
    recorder,
    *,
    model_name: str,
    language: str,
    glossary: str,
    backend: str,
    on_segment: Callable[[dict], None] | None = None,
    stop_event=None,
    poll_seconds: float = 1.0,
    sleep_fn: Callable[[float], None] | None = None,
    transcribe_fn: Callable[..., dict] | None = None,
) -> None:
    """Drain chunk ranges from `recorder` until stopped, then the remainder."""
    sleep = sleep_fn or time.sleep
    tail = ""
    consecutive_retries = 0

    def handle(rng) -> None:
        nonlocal tail, consecutive_retries
        start_byte, end_byte, _hard = rng
        start_seconds = start_byte / BYTES_PER_SECOND
        end_seconds = end_byte / BYTES_PER_SECOND
        pcm = session_mod.read_slice(session, start_byte, end_byte)

        if not pcm:
            # The range was announced but the bytes are not there. Record the
            # hole rather than dropping it silently.
            seg = {"start": start_seconds, "end": end_seconds,
                   "text": mark_gap(start_seconds, end_seconds),
                   "retried": False, "failed": True}
        else:
            prompt = glossary
            if tail:
                prompt = f"{glossary} {tail}".strip() if glossary else tail
            try:
                seg = transcribe_chunk(
                    pcm,
                    start_seconds=start_seconds,
                    model_name=model_name, language=language, prompt=prompt,
                    backend=backend,
                    allow_retry=consecutive_retries < MAX_CONSECUTIVE_RETRIES,
                    transcribe_fn=transcribe_fn,
                )
            except Exception as exc:  # noqa: BLE001
                # One bad chunk must not kill the worker. Losing this chunk is
                # survivable; losing the rest of the meeting is not.
                seg = {"start": start_seconds, "end": end_seconds,
                       "text": mark_gap(start_seconds, end_seconds),
                       "retried": False, "failed": True,
                       "error": f"{type(exc).__name__}: {exc}"}

        # A chunk that needed a retry keeps the counter climbing even when the
        # cap denied it the retry (retried=False, failed=True) -- otherwise a
        # permanently bad mic would alternate allow/deny forever instead of
        # staying capped off.
        needed_retry = seg["retried"] or seg["failed"]
        consecutive_retries = consecutive_retries + 1 if needed_retry else 0

        if not seg["failed"]:
            tail = seg["text"][-TAIL_CHARS:]
        session_mod.append_segment(session, seg)
        if on_segment is not None:
            on_segment(seg)

    while True:
        rng = recorder.pop_ready_chunk()
        if rng is not None:
            handle(rng)
            continue
        if stop_event is None or stop_event.is_set():
            break
        sleep(poll_seconds)

    final = recorder.flush_final_chunk()
    if final is not None:
        handle(final)
