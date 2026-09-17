"""End-to-end pipeline: audio file -> txt file."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from mynah.config import glossary as glossary_mod
from mynah.config import replacements as replacements_mod
from mynah.core import audio as audio_mod
from mynah.core import format as format_mod
from mynah.core import session as session_mod
from mynah.core import transcribe as transcribe_mod

ProgressCb = Callable[[str, str, float | None], None] | None
"""Progress callback: (stage, message, progress_0_to_1_or_none)"""


@dataclass
class PipelineOptions:
    diarize: bool = False
    timestamps: bool = False
    denoise: bool = False
    model: str = "large-v3"
    language: str = "ko"
    hf_token: str = ""


@dataclass
class PipelineResult:
    output_path: Path
    output_text: str
    stages_run: list[str] = field(default_factory=list)


def _unique_output_path(input_path: Path) -> Path:
    """Pick an output path that doesn't overwrite an existing file.

    `meeting.m4a` -> `meeting.txt` (or `meeting (1).txt`, `meeting (2).txt`, ...).
    """
    base = input_path.with_suffix(".txt")
    if not base.exists():
        return base
    parent = base.parent
    stem = base.stem
    n = 1
    while True:
        candidate = parent / f"{stem} ({n}).txt"
        if not candidate.exists():
            return candidate
        n += 1


def _writable_output_path(input_path: Path) -> Path:
    """Resolve an output path; fall back to ~/Documents/mynah-output/ if the
    input directory isn't writable."""
    try:
        candidate = _unique_output_path(input_path)
        candidate.parent.mkdir(parents=True, exist_ok=True)
        test = candidate.parent / f".mynah_write_test_{os.getpid()}"
        test.write_text("", encoding="utf-8")
        test.unlink()
        return candidate
    except (OSError, PermissionError):
        fallback_dir = Path.home() / "Documents" / "mynah-output"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        return _unique_output_path(fallback_dir / input_path.name)


def run(
    input_path: Path,
    options: PipelineOptions,
    *,
    on_progress: ProgressCb = None,
) -> PipelineResult:
    """Run the full pipeline for a single audio file."""
    input_path = Path(input_path).expanduser().resolve()
    stages_run: list[str] = []
    tmp_files: list[Path] = []

    def _emit(stage: str, message: str, progress: float | None = None) -> None:
        if on_progress:
            on_progress(stage, message, progress)

    try:
        _emit("audio", "normalizing input to 16kHz mono", 0.0)
        wav = audio_mod.to_wav_16k_mono(input_path)
        tmp_files.append(wav)
        stages_run.append("audio")
        _emit("audio", "normalized", 1.0)

        if options.denoise:
            from mynah.core import denoise as denoise_mod  # lazy
            _emit("denoise", "running demucs (vocals stem)", 0.0)
            wav = denoise_mod.denoise(wav)
            tmp_files.append(wav)
            stages_run.append("denoise")
            _emit("denoise", "denoised", 1.0)

        terms = glossary_mod.load()
        rules = replacements_mod.load()

        def _t_progress(message: str, p: float | None) -> None:
            _emit("transcribe", message, p)

        if options.diarize:
            # Speaker assignment needs WhisperX word-level alignment, which
            # only exists on the CPU path.
            result = transcribe_mod.transcribe(
                wav,
                model_name=options.model,
                language=options.language,
                initial_prompt=glossary_mod.as_initial_prompt(terms),
                hotwords=glossary_mod.as_hotwords(terms),
                align_words=True,
                on_progress=_t_progress,
            )
        else:
            from mynah.core.live import guard_segments

            # --timestamps reads segment starts, which every engine returns,
            # so only diarization is worth 0.86x realtime.
            _t_progress("transcribing", 0.0)
            result = transcribe_mod.transcribe_wav(
                wav,
                model_name=options.model,
                language=options.language,
                initial_prompt=glossary_mod.as_initial_prompt(terms),
            )
            guard_segments(result.get("segments", []))
            _t_progress("transcribed", 1.0)
        stages_run.append("transcribe")

        if options.diarize:
            from mynah.core import diarize as diarize_mod  # lazy

            def _d_progress(message: str, p: float | None) -> None:
                _emit("diarize", message, p)

            result = diarize_mod.diarize_and_assign(
                result,
                hf_token=options.hf_token,
                on_progress=_d_progress,
            )
            stages_run.append("diarize")

        _emit("format", "rendering output", 0.0)
        text = format_mod.render(
            result,
            diarize=options.diarize,
            timestamps=options.timestamps,
        )
        if rules:
            text = replacements_mod.apply(text, rules)

        out_path = _writable_output_path(input_path)
        out_path.write_text(text, encoding="utf-8")
        stages_run.append("format")
        _emit("format", f"wrote {out_path}", 1.0)

        return PipelineResult(
            output_path=out_path,
            output_text=text,
            stages_run=stages_run,
        )
    finally:
        for tmp in tmp_files:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


def segments_to_result(segments: list[dict], language: str = "ko") -> dict:
    """Adapt JSONL segments to the dict shape format.render() already takes."""
    return {"segments": segments, "language": language}


UNCOVERED_FLOOR_SECONDS = 5.0
"""Below this, the live worker simply drained normally — re-transcribing the
tail end would cost a model load for nothing."""


def has_uncovered_audio(session, segments: list[dict] | None = None) -> bool:
    """Does this session hold audio no segment covers? Whisper will be loaded
    during finalization if so."""
    if segments is None:
        segments = session_mod.read_segments(session)
    covered = max((s.get("end", 0.0) for s in segments), default=0.0)
    return session_mod.duration_seconds(session) - covered > UNCOVERED_FLOOR_SECONDS


def _transcribe_uncovered(session, options, segments: list[dict], emit) -> list[dict]:
    """Transcribe audio no segment covers, and return the updated segments.

    Two ways a session arrives here with untranscribed audio: live_transcribe
    was off, so no worker ever ran (the design's "transcribe after stop"
    fallback), or a crash killed the worker before its final chunk. Both are
    the same hole, so both get the same patch.
    """
    if not has_uncovered_audio(session, segments):
        return segments

    from mynah.core import live as live_mod  # lazy: pulls the ML stack

    covered = max((s.get("end", 0.0) for s in segments), default=0.0)
    total = session_mod.duration_seconds(session)
    emit("transcribe", f"transcribing {int(total - covered)}s not yet covered", 0.0)
    pcm = session_mod.read_slice(
        session,
        int(covered * session_mod.BYTES_PER_SECOND),
        session_mod.audio_bytes(session),
    )
    seg = live_mod.transcribe_chunk(
        pcm,
        start_seconds=covered,
        model_name=options.model,
        language=options.language,
        prompt=glossary_mod.as_initial_prompt(glossary_mod.load()),
        backend=str(session_mod.get_options(session).get("backend", "auto")),
    )
    session_mod.append_segment(session, seg)
    emit("transcribe", "transcribed remaining audio", 1.0)
    return session_mod.read_segments(session)


def finalize_session(
    session,
    options: PipelineOptions,
    *,
    on_progress: ProgressCb = None,
) -> PipelineResult:
    """Turn a recorded session into meeting.wav + meeting.txt.

    The same call serves a clean shutdown and a crash recovery — the WAV
    length comes from the PCM file size, and read_segments() skips any
    partially written final line.
    """
    def _emit(stage: str, message: str, progress: float | None = None) -> None:
        if on_progress:
            on_progress(stage, message, progress)

    session_mod.set_status(session, session_mod.STATUS_TRANSCRIBING)

    _emit("format", "packaging audio", 0.0)
    wav_path = session_mod.finalize_wav(session)
    _emit("format", f"packaged {wav_path.name}", 0.2)

    segments = session_mod.read_segments(session)

    if options.diarize:
        # Diarization needs word-level timestamps and global speaker
        # clustering across the whole meeting. Per-chunk live transcription
        # produces neither, so re-run the file pipeline over the finalized
        # WAV. This is the post-recording wait the design calls an
        # algorithmic constraint, not a design choice.
        _emit("diarize", "re-transcribing for speaker labels", 0.0)
        out = run(wav_path, options, on_progress=on_progress)
        session_mod.set_status(session, session_mod.STATUS_DONE)
        return out

    try:
        segments = _transcribe_uncovered(session, options, segments, _emit)
    except Exception as exc:  # noqa: BLE001
        # Better a transcript missing its tail than no transcript and a
        # session the recovery banner can never finish.
        _emit("transcribe", f"tail transcription failed: {exc}", 1.0)
    result = segments_to_result(segments, language=options.language)

    _emit("format", "rendering output", 0.5)
    text = format_mod.render(
        result, diarize=options.diarize, timestamps=options.timestamps,
    )
    rules = replacements_mod.load()
    if rules:
        text = replacements_mod.apply(text, rules)

    out_path = session.dir / f"{session.dir.name}.txt"
    out_path.write_text(text, encoding="utf-8")
    session_mod.set_status(session, session_mod.STATUS_DONE)
    _emit("format", f"wrote {out_path}", 1.0)

    return PipelineResult(
        output_path=out_path,
        output_text=text,
        stages_run=["format"],
    )
