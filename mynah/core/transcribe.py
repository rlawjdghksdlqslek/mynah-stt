"""WhisperX transcription wrapper.

WhisperX is loaded lazily so the rest of the package can be imported (and
tests can run) without the heavy ML stack installed.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Prevent ctranslate2 / tokenizers from forking subprocesses on macOS.
# Without this, Python's multiprocessing raises "bad value(s) in fds_to_keep"
# when Textual's async event loop has open file descriptors at model load time.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

ProgressCb = Callable[[str, float | None], None] | None


class TranscribeError(Exception):
    pass


def _import_whisperx():
    try:
        import whisperx  # type: ignore
    except ImportError as exc:
        raise TranscribeError(
            "whisperx is not installed. Run: pipx install -e . (or pip install whisperx)"
        ) from exc
    return whisperx


def pick_compute_type() -> str:
    """faster-whisper / CTranslate2 compute type for Apple Silicon CPU."""
    return "int8"


def transcribe(
    wav_path: Path,
    *,
    model_name: str = "large-v3",
    language: str = "ko",
    beam_size: int = 5,
    initial_prompt: str = "",
    hotwords: str = "",
    align_words: bool = False,
    on_progress: ProgressCb = None,
) -> dict[str, Any]:
    """Run WhisperX on the given 16kHz mono WAV file.

    Returns a dict with at least {'segments': [...], 'language': 'ko'}.
    If align_words=True, segments will contain word-level timestamps
    (used for both --timestamps formatting and as input for diarization).
    """
    whisperx = _import_whisperx()

    if on_progress:
        on_progress("loading model", None)

    asr_options: dict[str, Any] = {"beam_size": beam_size}
    if initial_prompt:
        asr_options["initial_prompt"] = initial_prompt
    if hotwords:
        asr_options["hotwords"] = hotwords

    model = whisperx.load_model(
        model_name,
        device="cpu",
        compute_type=pick_compute_type(),
        language=language if language != "auto" else None,
        asr_options=asr_options,
        vad_method="pyannote",
        vad_options={"vad_onset": 0.5, "vad_offset": 0.363},
    )

    if on_progress:
        on_progress("loading audio", None)

    audio = whisperx.load_audio(str(wav_path))

    if on_progress:
        on_progress("transcribing", 0.0)

    result = model.transcribe(
        audio,
        batch_size=8,
        language=language if language != "auto" else None,
    )

    if on_progress:
        on_progress("transcribing", 1.0)

    if align_words:
        if on_progress:
            on_progress("aligning words", 0.0)
        try:
            align_model, metadata = whisperx.load_align_model(
                language_code=result.get("language", language),
                device="cpu",
            )
            result = whisperx.align(
                result["segments"],
                align_model,
                metadata,
                audio,
                device="cpu",
                return_char_alignments=False,
            )
        except (ValueError, KeyError, RuntimeError) as exc:
            # Some languages don't have an alignment model bundled with WhisperX.
            # Continue without word-level timestamps.
            if on_progress:
                on_progress(f"alignment skipped ({exc})", 1.0)
        else:
            if on_progress:
                on_progress("aligning words", 1.0)

    # Stash the audio for downstream stages (diarization needs it)
    result.setdefault("language", language)
    result["_audio"] = audio
    return result
