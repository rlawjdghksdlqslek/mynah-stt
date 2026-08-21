"""Tests for the crash-safe session store."""

from __future__ import annotations

import json
import struct
import wave

from mynah.core import session as session_mod


def _pcm(samples: list[int]) -> bytes:
    return b"".join(struct.pack("<h", s) for s in samples)


class TestSessionCreate:
    def test_create_makes_directory_and_meta(self, tmp_path):
        s = session_mod.create({"language": "ko"}, root=tmp_path)

        assert s.dir.is_dir()
        assert s.meta_path.exists()
        meta = json.loads(s.meta_path.read_text(encoding="utf-8"))
        assert meta["status"] == "recording"
        assert meta["options"]["language"] == "ko"

    def test_create_uses_unique_directories(self, tmp_path):
        a = session_mod.create({}, root=tmp_path)
        b = session_mod.create({}, root=tmp_path)
        assert a.dir != b.dir


class TestAudioAppend:
    def test_append_and_read_slice(self, tmp_path):
        s = session_mod.create({}, root=tmp_path)
        session_mod.append_audio(s, _pcm([1, 2, 3, 4]))
        session_mod.append_audio(s, _pcm([5, 6]))

        assert session_mod.audio_bytes(s) == 12
        assert session_mod.read_slice(s, 0, 4) == _pcm([1, 2])
        assert session_mod.read_slice(s, 8, 12) == _pcm([5, 6])

    def test_duration_from_byte_count(self, tmp_path):
        s = session_mod.create({}, root=tmp_path)
        session_mod.append_audio(s, b"\x00" * session_mod.BYTES_PER_SECOND * 3)
        assert abs(session_mod.duration_seconds(s) - 3.0) < 0.001


class TestSegments:
    def test_append_and_read_segments(self, tmp_path):
        s = session_mod.create({}, root=tmp_path)
        session_mod.append_segment(s, {"start": 0.0, "end": 1.0, "text": "안녕"})
        session_mod.append_segment(s, {"start": 1.0, "end": 2.0, "text": "하세요"})

        segs = session_mod.read_segments(s)
        assert [x["text"] for x in segs] == ["안녕", "하세요"]

    def test_truncated_last_line_does_not_lose_earlier_lines(self, tmp_path):
        s = session_mod.create({}, root=tmp_path)
        session_mod.append_segment(s, {"start": 0.0, "end": 1.0, "text": "온전함"})
        # Simulate a crash mid-write: append a partial JSON line.
        with s.transcript_path.open("a", encoding="utf-8") as fp:
            fp.write('{"start": 1.0, "end"')

        segs = session_mod.read_segments(s)
        assert [x["text"] for x in segs] == ["온전함"]


class TestRecovery:
    def test_list_unfinished_finds_recording_session(self, tmp_path):
        s = session_mod.create({}, root=tmp_path)
        session_mod.append_audio(s, b"\x00" * 320)

        found = session_mod.list_unfinished(root=tmp_path)
        assert [x.dir for x in found] == [s.dir]

    def test_list_unfinished_skips_done(self, tmp_path):
        s = session_mod.create({}, root=tmp_path)
        session_mod.set_status(s, "done")
        assert session_mod.list_unfinished(root=tmp_path) == []

    def test_finalize_wav_produces_playable_file(self, tmp_path):
        s = session_mod.create({}, root=tmp_path)
        session_mod.append_audio(s, _pcm([100] * 16000))

        wav = session_mod.finalize_wav(s)

        with wave.open(str(wav), "rb") as w:
            assert w.getnchannels() == 1
            assert w.getsampwidth() == 2
            assert w.getframerate() == 16000
            assert w.getnframes() == 16000

    def test_finalize_wav_works_on_crashed_session(self, tmp_path):
        """No clean shutdown ever happened — the same call must still work."""
        s = session_mod.create({}, root=tmp_path)
        session_mod.append_audio(s, _pcm([7] * 8000))
        # status left at "recording", nothing closed

        wav = session_mod.finalize_wav(s)
        with wave.open(str(wav), "rb") as w:
            assert w.getnframes() == 8000
