"""Optional source-separation denoise via Demucs.

Demucs separates an audio file into stems (vocals/drums/bass/other). For
meeting recordings we keep just the 'vocals' stem, which suppresses HVAC
hum, keyboard typing, and other non-speech noise.

Demucs is heavy (PyTorch + a separate model). It is an optional dependency
(`pip install mynah[denoise]`); we import it lazily.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from mynah.core.audio import to_wav_16k_mono


class DenoiseError(Exception):
    pass


def _ensure_demucs_cli() -> None:
    if shutil.which("demucs") is None:
        raise DenoiseError(
            "demucs CLI not found. Install with: pipx install demucs "
            "(or `pip install mynah[denoise]`)"
        )


def denoise(input_audio: Path) -> Path:
    """Run Demucs to extract vocals; return the resulting 16kHz mono WAV path.

    The output is placed in a temp directory; caller is responsible for
    cleaning it up if desired. On failure, raises DenoiseError.
    """
    _ensure_demucs_cli()
    src = Path(input_audio).expanduser().resolve()
    if not src.exists():
        raise DenoiseError(f"File not found: {src}")

    workdir = Path(tempfile.mkdtemp(prefix="mynah_denoise_"))
    cmd = [
        "demucs",
        "--two-stems=vocals",
        "-n", "htdemucs",
        "-o", str(workdir),
        str(src),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise DenoiseError(
            f"demucs failed (exit {proc.returncode}):\n{proc.stderr.strip()}"
        )

    vocals = workdir / "htdemucs" / src.stem / "vocals.wav"
    if not vocals.exists():
        candidates = list(workdir.rglob("vocals.wav"))
        if not candidates:
            raise DenoiseError(f"demucs ran but produced no vocals.wav under {workdir}")
        vocals = candidates[0]

    normalized = workdir / "vocals_16k_mono.wav"
    return to_wav_16k_mono(vocals, normalized)
