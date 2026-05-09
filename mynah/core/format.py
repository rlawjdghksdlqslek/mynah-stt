"""Output formatters for transcription results.

WhisperX produces a result dict with a "segments" key. Each segment has:
    - start: float (seconds)
    - end:   float (seconds)
    - text:  str
    - speaker: str (only after diarization)
    - words: list[{word, start, end, score, speaker?}] (only after alignment)

We support four output modes by combining two flags:
    diarize=False, timestamps=False -> plain
    diarize=False, timestamps=True  -> timestamped
    diarize=True,  timestamps=False -> speaker-labeled
    diarize=True,  timestamps=True  -> speaker + timestamped
"""

from __future__ import annotations

from typing import Any

UNKNOWN_SPEAKER = "UNKNOWN"


def format_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS (zero-padded). Negative values clamp to zero."""
    if seconds < 0:
        seconds = 0.0
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_plain(result: dict[str, Any]) -> str:
    """Continuous text, segments joined with newlines."""
    lines = [seg.get("text", "").strip() for seg in result.get("segments", [])]
    return "\n".join(line for line in lines if line) + ("\n" if lines else "")


def format_timestamped(result: dict[str, Any]) -> str:
    """Each segment prefixed with [HH:MM:SS]."""
    out: list[str] = []
    for seg in result.get("segments", []):
        text = seg.get("text", "").strip()
        if not text:
            continue
        ts = format_timestamp(float(seg.get("start", 0.0)))
        out.append(f"[{ts}] {text}")
    return "\n".join(out) + ("\n" if out else "")


def _speaker_of(seg: dict[str, Any]) -> str:
    sp = seg.get("speaker")
    if sp:
        return str(sp)
    words = seg.get("words") or []
    for w in words:
        wsp = w.get("speaker")
        if wsp:
            return str(wsp)
    return UNKNOWN_SPEAKER


def format_speakers(result: dict[str, Any]) -> str:
    """Each segment prefixed with SPEAKER_NN: . Consecutive same-speaker segments
    are joined into one paragraph for readability."""
    out: list[str] = []
    current_speaker: str | None = None
    buffer: list[str] = []
    for seg in result.get("segments", []):
        text = seg.get("text", "").strip()
        if not text:
            continue
        sp = _speaker_of(seg)
        if sp != current_speaker:
            if buffer:
                out.append(f"{current_speaker}: {' '.join(buffer)}")
                buffer = []
            current_speaker = sp
        buffer.append(text)
    if buffer:
        out.append(f"{current_speaker}: {' '.join(buffer)}")
    return "\n".join(out) + ("\n" if out else "")


def format_speakers_timestamped(result: dict[str, Any]) -> str:
    """Each segment prefixed with [HH:MM:SS] SPEAKER_NN: ."""
    out: list[str] = []
    for seg in result.get("segments", []):
        text = seg.get("text", "").strip()
        if not text:
            continue
        ts = format_timestamp(float(seg.get("start", 0.0)))
        sp = _speaker_of(seg)
        out.append(f"[{ts}] {sp}: {text}")
    return "\n".join(out) + ("\n" if out else "")


def render(result: dict[str, Any], *, diarize: bool, timestamps: bool) -> str:
    """Pick the right formatter based on options."""
    if diarize and timestamps:
        return format_speakers_timestamped(result)
    if diarize:
        return format_speakers(result)
    if timestamps:
        return format_timestamped(result)
    return format_plain(result)
