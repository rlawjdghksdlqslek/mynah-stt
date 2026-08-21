"""Tests for audio normalization."""

from __future__ import annotations

import array
import math
import struct

from mynah.core import audio as audio_mod


def _pcm(samples: list[int]) -> bytes:
    return b"".join(struct.pack("<h", s) for s in samples)


def _rms(pcm: bytes) -> float:
    s = array.array("h")
    s.frombytes(pcm)
    return math.sqrt(sum(v * v for v in s) / len(s))


class TestNormalizeGain:
    def test_quiet_signal_is_amplified(self):
        # ~-44 dBFS, the level measured in the user's own recordings
        quiet = _pcm([200, -200] * 500)
        out = audio_mod.normalize_gain(quiet)

        assert _rms(out) > _rms(quiet) * 5

    def test_reaches_target_level(self):
        quiet = _pcm([200, -200] * 500)
        out = audio_mod.normalize_gain(quiet, target_dbfs=-18.0)

        target = (10 ** (-18.0 / 20.0)) * 32768.0
        assert math.isclose(_rms(out), target, rel_tol=0.05)

    def test_never_clips(self):
        loud_peaks = _pcm([30000, -30000] + [100] * 998)
        out = audio_mod.normalize_gain(loud_peaks)

        s = array.array("h")
        s.frombytes(out)
        assert max(abs(v) for v in s) <= 32767

    def test_already_loud_signal_is_left_alone(self):
        loud = _pcm([12000, -12000] * 500)  # already above target
        assert audio_mod.normalize_gain(loud) == loud

    def test_silence_is_returned_unchanged(self):
        silence = _pcm([0] * 100)
        assert audio_mod.normalize_gain(silence) == silence

    def test_empty_input(self):
        assert audio_mod.normalize_gain(b"") == b""

    def test_output_length_matches_input(self):
        quiet = _pcm([300, -300] * 400)
        assert len(audio_mod.normalize_gain(quiet)) == len(quiet)

    def test_full_scale_negative_sample_does_not_overflow(self):
        # int16 is asymmetric: min is -32768, max is +32767. The headroom cap
        # must use the true peak magnitude or this overflows.
        buf = _pcm([-32768, 100, -100, 100])
        out = audio_mod.normalize_gain(buf)

        s = array.array("h")
        s.frombytes(out)
        assert min(s) >= -32768
        assert max(s) <= 32767

    def test_odd_byte_count_is_truncated_not_raised(self):
        # A crash mid-write leaves a trailing odd byte.
        buf = _pcm([200, -200] * 500) + b"\x01"
        out = audio_mod.normalize_gain(buf)

        assert len(out) % 2 == 0


class TestFfmpegFilter:
    def test_loudnorm_is_in_the_command(self, monkeypatch, tmp_path):
        captured = {}

        class FakeProc:
            returncode = 0
            stderr = ""

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            # ffmpeg would create the file; fake it so the size check passes
            out = tmp_path / "out.wav"
            out.write_bytes(b"RIFF")
            return FakeProc()

        src = tmp_path / "in.wav"
        src.write_bytes(b"RIFF")
        monkeypatch.setattr(audio_mod, "ensure_ffmpeg", lambda: None)
        monkeypatch.setattr(audio_mod.subprocess, "run", fake_run)

        audio_mod.to_wav_16k_mono(src, tmp_path / "out.wav")

        assert "-af" in captured["cmd"]
        idx = captured["cmd"].index("-af")
        assert captured["cmd"][idx + 1] == audio_mod.LOUDNORM_FILTER
