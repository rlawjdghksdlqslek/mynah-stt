"""Audio normalization via ffmpeg (decode any input -> 16kHz mono WAV)."""

from __future__ import annotations

import audioop
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

SUPPORTED_INPUT_EXTS = {".m4a", ".mp3", ".wav", ".flac", ".ogg", ".webm", ".mp4", ".aac"}

# Real meeting recordings measured -36..-44 dBFS, 15-20 dB below normal speech
# level. Whisper hallucinates on low-SNR input: 12 of 28 transcripts made from
# those recordings contained a repetition loop, worst case one word repeated
# 219 times, which destroys the segment. Normalizing the level eliminated the
# loops on every clip tested. Do not lower the target without re-measuring.
LOUDNORM_FILTER = "loudnorm=I=-18:TP=-2:LRA=11"
TARGET_DBFS = -18.0
SAMPWIDTH = 2


class AudioError(Exception):
    pass


def ensure_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise AudioError("ffmpeg not found. Install: brew install ffmpeg")


def normalize_gain(pcm: bytes, target_dbfs: float = TARGET_DBFS) -> bytes:
    """Raise a quiet PCM buffer toward `target_dbfs` RMS without clipping.

    Only amplifies. A signal already at or above target is returned as-is —
    attenuating it would not improve signal-to-noise ratio.

    Used for the live-chunk path; file input goes through ffmpeg's loudnorm.
    """
    # audioop left the stdlib in 3.13; the audioop-lts dependency puts the
    # same module back. Switch to numpy only if that package stops shipping.
    if not pcm:
        return pcm
    if len(pcm) % SAMPWIDTH:
        # A crash can kill the recorder mid-sample, leaving a trailing odd
        # byte. Drop it rather than raising — losing 1/16000 s beats losing
        # the recovery.
        pcm = pcm[: len(pcm) - (len(pcm) % SAMPWIDTH)]
        if not pcm:
            return b""
    rms = audioop.rms(pcm, SAMPWIDTH)
    peak = audioop.max(pcm, SAMPWIDTH)
    if rms == 0 or peak == 0:
        return pcm

    target_rms = (10 ** (target_dbfs / 20.0)) * 32768.0
    gain = target_rms / rms
    gain = min(gain, 32767.0 / peak)  # headroom: never clip
    if gain <= 1.0:
        return pcm
    return audioop.mul(pcm, SAMPWIDTH, gain)


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
        "-af", LOUDNORM_FILTER,
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
