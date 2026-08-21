"""Crash-safe session store: one recording, one folder, three files.

    <root>/<session-id>/
        audio.pcm         raw 16 kHz mono int16, append-only, no header
        transcript.jsonl  one JSON object per completed chunk
        session.json      options + status

audio.pcm deliberately has no header. A WAV header carries the total length,
which can only be written when the file is closed — so a process that dies
mid-recording leaves an unreadable file. Headerless PCM is valid at every
instant; finalize_wav() adds the header afterwards, from the file size.
"""

from __future__ import annotations

import datetime as dt
import json
import wave
from dataclasses import dataclass
from pathlib import Path

SAMPLERATE = 16000
CHANNELS = 1
SAMPWIDTH = 2
BYTES_PER_SECOND = SAMPLERATE * SAMPWIDTH  # 32000

AUDIO_NAME = "audio.pcm"
TRANSCRIPT_NAME = "transcript.jsonl"
META_NAME = "session.json"

STATUS_RECORDING = "recording"
STATUS_TRANSCRIBING = "transcribing"
STATUS_DONE = "done"


def default_root() -> Path:
    return Path.home() / "Documents" / "mynah-recordings"


@dataclass(frozen=True)
class Session:
    dir: Path

    @property
    def audio_path(self) -> Path:
        return self.dir / AUDIO_NAME

    @property
    def transcript_path(self) -> Path:
        return self.dir / TRANSCRIPT_NAME

    @property
    def meta_path(self) -> Path:
        return self.dir / META_NAME


def _session_id(now: dt.datetime | None = None) -> str:
    return (now or dt.datetime.now()).strftime("%Y-%m-%d-%H%M%S")


def create(options: dict, root: Path | None = None) -> Session:
    root = Path(root) if root is not None else default_root()
    root.mkdir(parents=True, exist_ok=True)

    base = _session_id()
    target = root / base
    n = 1
    while target.exists():
        target = root / f"{base}-{n}"
        n += 1
    target.mkdir(parents=True)

    s = Session(dir=target)
    s.audio_path.touch()
    s.transcript_path.touch()
    _write_meta(s, {"status": STATUS_RECORDING, "options": options})
    return s


def open_session(directory: Path) -> Session:
    return Session(dir=Path(directory))


def _write_meta(s: Session, meta: dict) -> None:
    s.meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_meta(s: Session) -> dict:
    try:
        return json.loads(s.meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def get_status(s: Session) -> str:
    return str(_read_meta(s).get("status", STATUS_RECORDING))


def set_status(s: Session, status: str) -> None:
    meta = _read_meta(s)
    meta["status"] = status
    _write_meta(s, meta)


def get_options(s: Session) -> dict:
    return dict(_read_meta(s).get("options", {}))


def list_unfinished(root: Path | None = None) -> list[Session]:
    root = Path(root) if root is not None else default_root()
    if not root.is_dir():
        return []
    out = []
    for d in sorted(root.iterdir()):
        if not d.is_dir() or not (d / META_NAME).exists():
            continue
        s = Session(dir=d)
        if get_status(s) != STATUS_DONE:
            out.append(s)
    return out


def append_audio(s: Session, data: bytes) -> None:
    with s.audio_path.open("ab") as fp:
        fp.write(data)


def audio_bytes(s: Session) -> int:
    try:
        return s.audio_path.stat().st_size
    except OSError:
        return 0


def duration_seconds(s: Session) -> float:
    return audio_bytes(s) / BYTES_PER_SECOND


def read_slice(s: Session, start: int, end: int) -> bytes:
    with s.audio_path.open("rb") as fp:
        fp.seek(start)
        return fp.read(max(0, end - start))


def append_segment(s: Session, seg: dict) -> None:
    with s.transcript_path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(seg, ensure_ascii=False) + "\n")


def read_segments(s: Session) -> list[dict]:
    """Parse the JSONL transcript, skipping any line that isn't valid JSON.

    A crash can leave a partially-written final line; earlier lines are intact
    and must survive.
    """
    if not s.transcript_path.exists():
        return []
    out = []
    for line in s.transcript_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def finalize_wav(s: Session, dst: Path | None = None) -> Path:
    """Wrap audio.pcm into a playable WAV. Same call for clean shutdown and
    for crash recovery — length comes from the file size either way."""
    dst = Path(dst) if dst is not None else s.dir / "meeting.wav"
    with s.audio_path.open("rb") as src, wave.open(str(dst), "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(SAMPWIDTH)
        w.setframerate(SAMPLERATE)
        while True:
            block = src.read(1 << 20)
            if not block:
                break
            w.writeframes(block)
    return dst
