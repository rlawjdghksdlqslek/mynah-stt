"""Microphone capture via sounddevice.

Audio is appended to a headerless raw PCM file. A WAV header stores the total
length and can only be written on close, so a process killed mid-recording
leaves an unreadable WAV. Raw PCM has no header to corrupt — it is valid at
every instant. session.finalize_wav() adds the header afterwards.

The audio callback never touches the UI. It appends bytes and updates one
float. The UI polls `level` on its own timer. Pushing into Textual from this
thread (which CoreAudio owns) risks overrunning the 64 ms budget, and an
overrun makes CoreAudio drop the next buffer — so UI lag became lost audio.
"""

from __future__ import annotations

import array
import math
import threading
from pathlib import Path


class RecordError(Exception):
    pass


def rms_from_int16(buffer: bytes) -> float:
    """Compute normalized RMS (0..1) from int16 little-endian PCM bytes.

    Returns 0.0 for empty input. Uses pure stdlib (array + math) so this
    function — and hence the level meter in the TUI — has zero deps.
    """
    if not buffer:
        return 0.0
    samples = array.array("h")
    samples.frombytes(buffer)
    if not samples:
        return 0.0
    sum_sq = sum(s * s for s in samples)
    rms = math.sqrt(sum_sq / len(samples))
    return min(1.0, rms / 32768.0)


def _import_sd():
    try:
        import sounddevice as sd  # type: ignore
    except ImportError as exc:
        raise RecordError(
            "sounddevice not installed. Install: pip install sounddevice"
        ) from exc
    return sd


MIN_CHUNK_SECONDS = 60.0
MAX_CHUNK_SECONDS = 90.0
SILENCE_SECONDS = 0.4


def silence_threshold(levels: list[float]) -> float:
    """Where 'quiet' sits for this particular room.

    Absolute thresholds fail: a quiet home office and a noisy meeting room
    have different noise floors. Sit between this room's floor and its
    typical speech level, closer to the floor.
    """
    if not levels:
        return 0.0
    ordered = sorted(levels)
    p20 = ordered[len(ordered) // 5]
    median = ordered[len(ordered) // 2]
    # A threshold at or above the median would mark speech itself as silence
    # (constant-level input is the degenerate case: p20 == median). Cap it
    # below speech level so "quiet" always means quiet relative to this room.
    return min(max(p20 * 1.5, median * 0.25), median * 0.5)


def find_cut(levels: list[float], start_frame: int, thresh: float) -> tuple[int, bool] | None:
    """Where should the chunk starting at `start_frame` end?

    Returns (end_frame, was_hard_cut), or None if not enough audio yet.
    Cutting mid-word costs accuracy, so wait for a silence gap once past the
    minimum; give up at the ceiling.
    """
    fps = AudioRecorder.SAMPLERATE / AudioRecorder.BLOCKSIZE
    min_f = int(MIN_CHUNK_SECONDS * fps)
    max_f = int(MAX_CHUNK_SECONDS * fps)
    need = max(1, int(SILENCE_SECONDS * fps))

    available = len(levels) - start_frame
    if available < min_f:
        return None

    run = 0
    for i in range(start_frame + min_f, min(start_frame + max_f, len(levels))):
        run = run + 1 if levels[i] < thresh else 0
        if run >= need:
            return i, False

    if available >= max_f:
        return start_frame + max_f, True
    return None


class AudioRecorder:
    """Captures mono int16 PCM at 16 kHz from the system default mic.

    Audio is streamed to a raw PCM file as it arrives — nothing is held in
    memory beyond a single callback chunk, so multi-hour meetings do not
    leak memory.

    Thread safety: the audio callback runs on a sounddevice-owned thread.
    All shared state (paused flag, frame count, level, file handle) is
    guarded by `_lock`.

    Resuming a session: `base_byte` is the size the PCM file already has.
    `_levels` deliberately holds only *this* run's frames — silence_threshold
    sorts the whole list, so pre-filling it with the previous run's levels
    would make "quiet" mean quiet for a different room. Byte offsets stay
    absolute within the file instead: frame indices are local, and
    `base_byte` is added on the way out.
    """

    SAMPLERATE = 16000
    CHANNELS = 1
    DTYPE = "int16"
    BLOCKSIZE = 1024  # ~64 ms per callback at 16 kHz
    LEVEL_EVERY = 4   # compute RMS on every Nth callback (~4 Hz)

    def __init__(self, output_path: Path, base_byte: int = 0) -> None:
        self.output_path = Path(output_path)
        self._base_byte = int(base_byte)
        self._sd = None
        self._stream = None
        self._fp = None
        self._lock = threading.Lock()
        self._paused = False
        self._frames_written = 0
        self._level = 0.0
        self._callback_count = 0
        self._is_running = False
        self._levels: list[float] = []
        self._cut_frame = 0

    @property
    def duration_seconds(self) -> float:
        with self._lock:
            return self._frames_written / self.SAMPLERATE

    @property
    def is_paused(self) -> bool:
        with self._lock:
            return self._paused

    @property
    def level(self) -> float:
        """Most recent normalized RMS (0..1). Read by the UI timer."""
        with self._lock:
            return self._level

    def start(self) -> None:
        if self._is_running:
            return
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._sd = _import_sd()
        self._fp = self.output_path.open("ab")
        self._stream = self._sd.InputStream(
            samplerate=self.SAMPLERATE,
            channels=self.CHANNELS,
            dtype=self.DTYPE,
            blocksize=self.BLOCKSIZE,
            callback=self._callback,
        )
        self._stream.start()
        self._is_running = True

    def stop(self) -> Path:
        if not self._is_running:
            return self.output_path
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            with self._lock:
                if self._fp is not None:
                    self._fp.flush()
                    self._fp.close()
                    self._fp = None
            self._is_running = False
        return self.output_path

    def pause(self) -> None:
        with self._lock:
            self._paused = True

    def resume(self) -> None:
        with self._lock:
            self._paused = False

    def pop_ready_chunk(self) -> tuple[int, int, bool] | None:
        """Byte range of the next completed chunk, or None if not ready.

        Ranges index into the growing PCM file — no per-chunk files exist.
        The third element says whether the cut was forced by the ceiling
        rather than found at silence; it is diagnostic only.
        """
        with self._lock:
            levels = list(self._levels)
            start = self._cut_frame
        found = find_cut(levels, start, silence_threshold(levels))
        if found is None:
            return None
        end_frame, hard = found
        with self._lock:
            self._cut_frame = end_frame
        bpf = self.BLOCKSIZE * 2
        return self._base_byte + start * bpf, self._base_byte + end_frame * bpf, hard

    def flush_final_chunk(self) -> tuple[int, int, bool] | None:
        """Whatever is left after stop(). None if nothing remains."""
        with self._lock:
            start = self._cut_frame
            total = len(self._levels)
            self._cut_frame = total
        if total <= start:
            return None
        bpf = self.BLOCKSIZE * 2
        return self._base_byte + start * bpf, self._base_byte + total * bpf, False

    def _callback(self, indata, frames, time_info, status) -> None:
        with self._lock:
            if self._paused:
                return
            data = bytes(indata)
            if self._fp is not None:
                self._fp.write(data)
                self._frames_written += frames
            n = self._callback_count
            self._callback_count += 1

        if n % self.LEVEL_EVERY == 0:
            level = rms_from_int16(data)
        else:
            level = None

        with self._lock:
            if level is not None:
                self._level = level
            # One entry per callback keeps frame indices aligned with the
            # byte offsets in the PCM file; repeat the last level between
            # measurements.
            self._levels.append(self._level)
