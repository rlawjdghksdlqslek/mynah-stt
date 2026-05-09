"""Audio normalization via ffmpeg (decode any input -> 16kHz mono WAV)."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

SUPPORTED_INPUT_EXTS = {".m4a", ".mp3", ".wav", ".flac", ".ogg", ".webm", ".mp4", ".aac"}


class AudioError(Exception):
    pass


def ensure_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise AudioError("ffmpeg not found. Install: brew install ffmpeg")


def to_wav_16k_mono(src: Path, dst: Path | None = None) -> Path:
    """Decode any audio file to 16 kHz mono WAV (Whisper's expected input).

    If dst is None, a temp file is created in the system temp dir.
    Returns the path to the produced WAV.
    """
    ensure_ffmpeg()
    src = Path(src).expanduser().resolve()
    if not src.exists():
        raise AudioError(f"File not found: {src}")
    if not src.is_file():
        raise AudioError(f"Not a regular file: {src}")
    if src.suffix.lower() not in SUPPORTED_INPUT_EXTS:
        raise AudioError(
            f"Unsupported audio format {src.suffix!r}. "
            f"Supported: {', '.join(sorted(SUPPORTED_INPUT_EXTS))}"
        )

    if dst is None:
        fd, name = tempfile.mkstemp(suffix=".wav", prefix="mynah_")
        os.close(fd)
        dst = Path(name)
    dst = Path(dst).expanduser()

    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel", "error",
        "-i", str(src),
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        str(dst),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AudioError(
            f"ffmpeg failed (exit {proc.returncode}):\n{proc.stderr.strip()}"
        )
    if not dst.exists() or dst.stat().st_size == 0:
        raise AudioError(f"ffmpeg produced no output at {dst}")
    return dst
