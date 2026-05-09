"""Detect whether the Whisper model has been downloaded yet.

WhisperX delegates inference to faster-whisper, which downloads the
CTranslate2-converted model from the `Systran/faster-whisper-*` repos
on HuggingFace. The standard HF cache layout is:

    ~/.cache/huggingface/hub/models--<owner>--<repo>/

This detection is heuristic: we only check for the directory's
existence, not whether the snapshot is complete. Good enough to
surface a "first-run, this will take a while" message — not load
bearing for correctness.
"""

from __future__ import annotations

from pathlib import Path

_HF_CACHE_DIR = Path.home() / ".cache" / "huggingface" / "hub"

_MODEL_DIR_BY_NAME = {
    "large-v3": "models--Systran--faster-whisper-large-v3",
    "large-v3-turbo": "models--Systran--faster-whisper-large-v3-turbo",
    "turbo": "models--Systran--faster-whisper-large-v3-turbo",
}


def is_whisper_cached(model: str = "large-v3") -> bool:
    """Return True if the named model appears to be in the HF cache."""
    if not _HF_CACHE_DIR.exists():
        return False
    dir_name = _MODEL_DIR_BY_NAME.get(model)
    if dir_name is None:
        return False
    return (_HF_CACHE_DIR / dir_name).exists()
