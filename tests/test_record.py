"""Tests for the microphone recording module."""

from __future__ import annotations

import math
import struct
import wave
from unittest.mock import MagicMock

import pytest

from mynah.core import record


def _int16_bytes(samples: list[int]) -> bytes:
    """Pack a list of int16 samples into little-endian bytes."""
    return b"".join(struct.pack("<h", s) for s in samples)


class TestRmsFromInt16:
    def test_silence_returns_zero(self) -> None:
        assert record.rms_from_int16(_int16_bytes([0, 0, 0, 0])) == 0.0

    def test_empty_buffer_returns_zero(self) -> None:
        assert record.rms_from_int16(b"") == 0.0

    def test_full_scale_returns_near_one(self) -> None:
        # 32767 is the max int16 positive value
        result = record.rms_from_int16(_int16_bytes([32767, 32767, 32767, 32767]))
        assert math.isclose(result, 1.0, abs_tol=0.001)

    def test_half_amplitude_is_half(self) -> None:
        result = record.rms_from_int16(_int16_bytes([16384] * 8))
        assert math.isclose(result, 0.5, abs_tol=0.01)

    def test_mixed_samples(self) -> None:
        # RMS of [1000, -1000, 1000, -1000] = 1000
        result = record.rms_from_int16(_int16_bytes([1000, -1000, 1000, -1000]))
        assert math.isclose(result, 1000 / 32768, abs_tol=0.001)


class FakeSDModule:
    """Stand-in for the `sounddevice` module."""

    def __init__(self) -> None:
        self.last_kwargs: dict | None = None
        self.streams: list[MagicMock] = []

    def InputStream(self, **kwargs):  # noqa: N802 — mirror sd's API
        self.last_kwargs = kwargs
        stream = MagicMock(name="FakeInputStream")
        self.streams.append(stream)
        return stream


@pytest.fixture
def fake_sd(monkeypatch):
    fake = FakeSDModule()
    monkeypatch.setattr(record, "_import_sd", lambda: fake)
    return fake


class TestAudioRecorderLifecycle:
    def test_start_creates_wav_with_correct_header(self, fake_sd, tmp_path):
        out = tmp_path / "rec.wav"
        rec = record.AudioRecorder(output_path=out)
        rec.start()
        rec.stop()

        # Re-open WAV to inspect header
        with wave.open(str(out), "rb") as w:
            assert w.getnchannels() == 1
            assert w.getsampwidth() == 2
            assert w.getframerate() == 16000

    def test_start_creates_input_stream_with_correct_params(self, fake_sd, tmp_path):
        rec = record.AudioRecorder(output_path=tmp_path / "rec.wav")
        rec.start()

        assert fake_sd.last_kwargs is not None
        assert fake_sd.last_kwargs["samplerate"] == 16000
        assert fake_sd.last_kwargs["channels"] == 1
        assert fake_sd.last_kwargs["dtype"] == "int16"
        assert "callback" in fake_sd.last_kwargs

        rec.stop()

    def test_start_calls_stream_start(self, fake_sd, tmp_path):
        rec = record.AudioRecorder(output_path=tmp_path / "rec.wav")
        rec.start()

        assert fake_sd.streams[0].start.called

        rec.stop()

    def test_stop_closes_stream_and_returns_path(self, fake_sd, tmp_path):
        out = tmp_path / "rec.wav"
        rec = record.AudioRecorder(output_path=out)
        rec.start()
        result = rec.stop()

        stream = fake_sd.streams[0]
        assert stream.stop.called
        assert stream.close.called
        assert result == out

    def test_start_creates_parent_directory(self, fake_sd, tmp_path):
        nested = tmp_path / "a" / "b" / "rec.wav"
        rec = record.AudioRecorder(output_path=nested)
        rec.start()
        rec.stop()

        assert nested.parent.is_dir()

    def test_double_start_is_noop(self, fake_sd, tmp_path):
        rec = record.AudioRecorder(output_path=tmp_path / "rec.wav")
        rec.start()
        rec.start()  # second start should not raise or open another stream

        assert len(fake_sd.streams) == 1

        rec.stop()


class TestAudioRecorderCallback:
    def test_callback_writes_frames_to_wav(self, fake_sd, tmp_path):
        out = tmp_path / "rec.wav"
        rec = record.AudioRecorder(output_path=out)
        rec.start()

        # 4 samples = 8 bytes
        chunk = _int16_bytes([100, 200, 300, 400])
        rec._callback(chunk, 4, None, None)

        rec.stop()

        with wave.open(str(out), "rb") as w:
            assert w.getnframes() == 4
            assert w.readframes(4) == chunk

    def test_callback_emits_level(self, fake_sd, tmp_path):
        levels: list[float] = []
        rec = record.AudioRecorder(
            output_path=tmp_path / "rec.wav",
            on_level=levels.append,
        )
        rec.start()

        rec._callback(_int16_bytes([16384] * 8), 8, None, None)

        rec.stop()

        assert len(levels) == 1
        assert math.isclose(levels[0], 0.5, abs_tol=0.01)

    def test_callback_updates_duration(self, fake_sd, tmp_path):
        rec = record.AudioRecorder(output_path=tmp_path / "rec.wav")
        rec.start()

        rec._callback(_int16_bytes([0] * 16000), 16000, None, None)

        assert math.isclose(rec.duration_seconds, 1.0, abs_tol=0.001)

        rec.stop()

    def test_level_callback_exception_does_not_crash(self, fake_sd, tmp_path):
        def boom(_level: float) -> None:
            raise RuntimeError("boom")

        rec = record.AudioRecorder(
            output_path=tmp_path / "rec.wav",
            on_level=boom,
        )
        rec.start()
        rec._callback(_int16_bytes([1000] * 4), 4, None, None)  # must not raise
        rec.stop()


class TestAudioRecorderPause:
    def test_pause_drops_frames(self, fake_sd, tmp_path):
        out = tmp_path / "rec.wav"
        rec = record.AudioRecorder(output_path=out)
        rec.start()

        rec._callback(_int16_bytes([100] * 4), 4, None, None)
        rec.pause()
        rec._callback(_int16_bytes([999] * 4), 4, None, None)  # dropped
        rec.resume()
        rec._callback(_int16_bytes([200] * 4), 4, None, None)

        rec.stop()

        with wave.open(str(out), "rb") as w:
            # 4 (pre-pause) + 0 (paused) + 4 (resumed) = 8 frames
            assert w.getnframes() == 8

    def test_pause_freezes_duration(self, fake_sd, tmp_path):
        rec = record.AudioRecorder(output_path=tmp_path / "rec.wav")
        rec.start()
        rec._callback(_int16_bytes([0] * 8000), 8000, None, None)  # 0.5s

        rec.pause()
        rec._callback(_int16_bytes([0] * 16000), 16000, None, None)  # ignored
        assert math.isclose(rec.duration_seconds, 0.5, abs_tol=0.001)
        assert rec.is_paused is True

        rec.resume()
        assert rec.is_paused is False
        rec.stop()

    def test_pause_does_not_emit_level(self, fake_sd, tmp_path):
        levels: list[float] = []
        rec = record.AudioRecorder(
            output_path=tmp_path / "rec.wav",
            on_level=levels.append,
        )
        rec.start()
        rec.pause()
        rec._callback(_int16_bytes([32767] * 8), 8, None, None)
        rec.stop()

        assert levels == []
