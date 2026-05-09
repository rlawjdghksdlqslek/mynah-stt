"""Microphone capture via sounddevice.

The actual audio capture is performed by macOS CoreAudio; sounddevice is
just a thin wrapper that gives us a clean Python callback API. We import
sounddevice lazily so unit tests can mock it without requiring the
system-level PortAudio/CoreAudio install on the test machine.
"""

from __future__ import annotations

import array
import math
import threading
import wave
from collections.abc import Callable
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


class AudioRecorder:
    """Captures mono int16 PCM at 16 kHz from the system default mic.

    Audio is streamed to a WAV file as it arrives — nothing is held in
    memory beyond a single callback chunk, so multi-hour meetings do not
    leak memory.

    Thread safety: the audio callback runs on a sounddevice-owned thread.
    All shared state (paused flag, frame count, WAV file handle) is
    guarded by `_lock`.
    """

    SAMPLERATE = 16000
    CHANNELS = 1
    DTYPE = "int16"
    BLOCKSIZE = 1024  # ~64 ms per callback at 16 kHz

    def __init__(
        self,
        output_path: Path,
        on_level: Callable[[float], None] | None = None,
    ) -> None:
        self.output_path = Path(output_path)
        self.on_level = on_level
        self._sd = None
        self._stream = None
        self._wav: wave.Wave_write | None = None
        self._lock = threading.Lock()
        self._paused = False
        self._frames_written = 0
        self._is_running = False

    @property
    def duration_seconds(self) -> float:
        with self._lock:
            return self._frames_written / self.SAMPLERATE

    @property
    def is_paused(self) -> bool:
        with self._lock:
            return self._paused

    def start(self) -> None:
        if self._is_running:
            return
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._sd = _import_sd()
        self._wav = wave.open(str(self.output_path), "wb")
        self._wav.setnchannels(self.CHANNELS)
        self._wav.setsampwidth(2)
        self._wav.setframerate(self.SAMPLERATE)
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
                if self._wav is not None:
                    self._wav.close()
                    self._wav = None
            self._is_running = False
        return self.output_path

    def pause(self) -> None:
        with self._lock:
            self._paused = True

    def resume(self) -> None:
        with self._lock:
            self._paused = False

    def _callback(self, indata, frames, time_info, status) -> None:
        # Snapshot pause state under lock, then act outside it.
        with self._lock:
            paused = self._paused
        if paused:
            return

        data = bytes(indata)

        with self._lock:
            if self._wav is not None:
                self._wav.writeframes(data)
                self._frames_written += frames

        if self.on_level is not None:
            try:
                self.on_level(rms_from_int16(data))
            except Exception:
                # Callback errors must not propagate into the audio
                # thread — they would silently kill the stream.
                pass
