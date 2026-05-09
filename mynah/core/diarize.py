"""Speaker diarization via pyannote-audio (through WhisperX wrapper).

Diarization needs:
  1. A HuggingFace token (free, requires acceptance of pyannote model terms).
  2. Word-level timestamps from `transcribe.transcribe(..., align_words=True)`,
     so we can map words to speaker segments.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

ProgressCb = Callable[[str, float | None], None] | None

PYANNOTE_TERMS_URL = "https://hf.co/pyannote/speaker-diarization-3.1"


class DiarizeError(Exception):
    pass


def _import_whisperx():
    try:
        import whisperx  # type: ignore
    except ImportError as exc:
        raise DiarizeError(
            "whisperx is not installed. Run: pipx install -e ."
        ) from exc
    return whisperx


def diarize_and_assign(
    result: dict[str, Any],
    *,
    hf_token: str,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    on_progress: ProgressCb = None,
) -> dict[str, Any]:
    """Run pyannote diarization and assign speakers to each word/segment.

    Mutates and returns `result`. Removes the cached audio array on exit.
    """
    if not hf_token:
        raise DiarizeError(
            "HuggingFace token not configured. Run: mynah --setup\n"
            f"You also need to accept the pyannote model terms at: {PYANNOTE_TERMS_URL}"
        )
    audio = result.get("_audio")
    if audio is None:
        raise DiarizeError(
            "No cached audio found in transcription result; "
            "diarization requires running transcribe() with align_words=True first."
        )
    if not result.get("segments"):
        return result

    whisperx = _import_whisperx()

    if on_progress:
        on_progress("loading diarization model", None)

    try:
        # WhisperX 3.1+ class name
        DiarPipeline = getattr(whisperx, "DiarizationPipeline", None)
        if DiarPipeline is None:
            from whisperx.diarize import DiarizationPipeline as DiarPipeline  # type: ignore
    except ImportError as exc:
        raise DiarizeError(
            "pyannote-audio not available; reinstall whisperx with diarization support."
        ) from exc

    pipeline = DiarPipeline(use_auth_token=hf_token, device="cpu")

    if on_progress:
        on_progress("diarizing", 0.0)

    diar_segments = pipeline(
        audio,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
    )

    if on_progress:
        on_progress("assigning speakers", 0.0)

    assigned = whisperx.assign_word_speakers(diar_segments, result)
    # `_audio` is a large numpy array; don't carry it past this stage.
    assigned.pop("_audio", None)
    if on_progress:
        on_progress("assigning speakers", 1.0)
    return assigned
