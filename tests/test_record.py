"""Tests for the microphone recording module."""

from __future__ import annotations

import math
import struct
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
    def test_start_creates_empty_pcm_file(self, fake_sd, tmp_path):
        out = tmp_path / "rec.pcm"
        rec = record.AudioRecorder(output_path=out)
        rec.start()
        rec.stop()

        # Headerless: an untouched recording is a zero-byte file, not a header.
        assert out.exists()
        assert out.stat().st_size == 0

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
    def test_callback_appends_raw_bytes(self, fake_sd, tmp_path):
        out = tmp_path / "rec.pcm"
        rec = record.AudioRecorder(output_path=out)
        rec.start()

        chunk = _int16_bytes([100, 200, 300, 400])
        rec._callback(chunk, 4, None, None)
        rec.stop()

        assert out.read_bytes() == chunk

    def test_level_property_reflects_last_callback(self, fake_sd, tmp_path):
        rec = record.AudioRecorder(output_path=tmp_path / "rec.pcm")
        rec.start()

        assert rec.level == 0.0
        rec._callback(_int16_bytes([16384] * 8), 8, None, None)

        assert math.isclose(rec.level, 0.5, abs_tol=0.01)
        rec.stop()

    def test_callback_updates_duration(self, fake_sd, tmp_path):
        rec = record.AudioRecorder(output_path=tmp_path / "rec.wav")
        rec.start()

        rec._callback(_int16_bytes([0] * 16000), 16000, None, None)

        assert math.isclose(rec.duration_seconds, 1.0, abs_tol=0.001)

        rec.stop()


class TestAudioRecorderPause:
    def test_pause_drops_frames(self, fake_sd, tmp_path):
        out = tmp_path / "rec.pcm"
        rec = record.AudioRecorder(output_path=out)
        rec.start()

        rec._callback(_int16_bytes([100] * 4), 4, None, None)
        rec.pause()
        rec._callback(_int16_bytes([999] * 4), 4, None, None)  # dropped
        rec.resume()
        rec._callback(_int16_bytes([200] * 4), 4, None, None)

        rec.stop()

        # 4 + 0 + 4 frames = 8 samples = 16 bytes
        assert out.stat().st_size == 16

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

    def test_pause_leaves_level_untouched(self, fake_sd, tmp_path):
        rec = record.AudioRecorder(output_path=tmp_path / "rec.pcm")
        rec.start()
        rec._callback(_int16_bytes([1000] * 8), 8, None, None)
        before = rec.level

        rec.pause()
        rec._callback(_int16_bytes([32767] * 8), 8, None, None)
        rec.stop()

        assert rec.level == before


class TestChunkBoundaries:
    FPS = record.AudioRecorder.SAMPLERATE / record.AudioRecorder.BLOCKSIZE

    def test_no_cut_before_minimum(self):
        levels = [0.5] * int(30 * self.FPS)
        assert record.find_cut(levels, 0, 0.01) is None

    def test_hard_cut_when_never_quiet(self):
        levels = [0.5] * int(200 * self.FPS)
        cut, hard = record.find_cut(levels, 0, 0.01)

        assert hard is True
        assert cut == int(record.MAX_CHUNK_SECONDS * self.FPS)

    def test_cuts_at_silence_after_minimum(self):
        levels = [0.5] * int(200 * self.FPS)
        at = int(70 * self.FPS)
        for i in range(at, at + int(0.5 * self.FPS)):
            levels[i] = 0.0

        cut, hard = record.find_cut(levels, 0, 0.01)

        assert hard is False
        assert int(69 * self.FPS) < cut < int(72 * self.FPS)

    def test_brief_silence_is_not_enough(self):
        levels = [0.5] * int(200 * self.FPS)
        at = int(70 * self.FPS)
        for i in range(at, at + 2):  # ~0.13s, below SILENCE_SECONDS
            levels[i] = 0.0

        cut, hard = record.find_cut(levels, 0, 0.01)
        assert hard is True  # fell through to the 90s ceiling

    def test_second_chunk_starts_from_previous_cut(self):
        levels = [0.5] * int(300 * self.FPS)
        first, _ = record.find_cut(levels, 0, 0.01)
        second, _ = record.find_cut(levels, first, 0.01)

        assert second - first == int(record.MAX_CHUNK_SECONDS * self.FPS)

    def test_threshold_sits_above_noise_floor(self):
        quiet_room = [0.001] * 50 + [0.3] * 50
        assert record.silence_threshold(quiet_room) > 0.001

    def test_threshold_scales_with_loud_room(self):
        quiet = record.silence_threshold([0.001] * 50 + [0.30] * 50)
        loud = record.silence_threshold([0.010] * 50 + [0.60] * 50)
        assert loud > quiet


class TestRecorderChunks:
    def test_pop_ready_chunk_returns_byte_range(self, fake_sd, tmp_path):
        rec = record.AudioRecorder(output_path=tmp_path / "rec.pcm")
        rec.start()

        block = _int16_bytes([20000] * record.AudioRecorder.BLOCKSIZE)
        fps = record.AudioRecorder.SAMPLERATE / record.AudioRecorder.BLOCKSIZE
        for _ in range(int(record.MAX_CHUNK_SECONDS * fps) + 1):
            rec._callback(block, record.AudioRecorder.BLOCKSIZE, None, None)

        got = rec.pop_ready_chunk()
        rec.stop()

        assert got is not None
        start, end, hard = got
        assert start == 0
        assert hard is True
        assert end == int(record.MAX_CHUNK_SECONDS * fps) * record.AudioRecorder.BLOCKSIZE * 2

    def test_resumed_recorder_offsets_ranges_past_existing_audio(self, fake_sd, tmp_path):
        out = tmp_path / "rec.pcm"
        out.write_bytes(b"\x00" * 64000)  # 2 s of prior audio
        rec = record.AudioRecorder(output_path=out, base_byte=64000)
        rec.start()

        block = _int16_bytes([20000] * record.AudioRecorder.BLOCKSIZE)
        fps = record.AudioRecorder.SAMPLERATE / record.AudioRecorder.BLOCKSIZE
        for _ in range(int(record.MAX_CHUNK_SECONDS * fps) + 1):
            rec._callback(block, record.AudioRecorder.BLOCKSIZE, None, None)

        start, end, _hard = rec.pop_ready_chunk()
        rec.stop()

        # Must not point back into the audio from the previous run.
        assert start == 64000
        assert end > 64000

    def test_pop_ready_chunk_none_when_too_short(self, fake_sd, tmp_path):
        rec = record.AudioRecorder(output_path=tmp_path / "rec.pcm")
        rec.start()
        rec._callback(_int16_bytes([100] * 1024), 1024, None, None)

        assert rec.pop_ready_chunk() is None
        rec.stop()

    def test_flush_final_chunk_returns_remainder(self, fake_sd, tmp_path):
        rec = record.AudioRecorder(output_path=tmp_path / "rec.pcm")
        rec.start()
        rec._callback(_int16_bytes([100] * 1024), 1024, None, None)
        rec.stop()

        got = rec.flush_final_chunk()
        assert got == (0, 2048, False)

    def test_flush_final_chunk_none_when_empty(self, fake_sd, tmp_path):
        rec = record.AudioRecorder(output_path=tmp_path / "rec.pcm")
        rec.start()
        rec.stop()

        assert rec.flush_final_chunk() is None


class TestStopIsNotReentrant:
    """Pressing Stop twice used to finalize the same session twice.

    The old guard only checked that a recorder existed, and `stop()` does not
    clear it, so a second press ran the whole body again: a second
    ProgressScreen, a second finalize_session, and a tail that could be
    transcribed and appended twice.
    """

    def test_second_stop_returns_before_touching_anything(self):
        import asyncio

        from mynah.tui.screens.record import RecordScreen

        screen = RecordScreen.__new__(RecordScreen)
        screen._recorder = object()  # non-None, as it is after the first stop
        screen._stopping = True

        # Without the guard this reaches `self._recorder.stop()` and raises.
        asyncio.run(screen.action_stop())
