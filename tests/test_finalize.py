"""Session finalization: JSONL -> rendered txt + playable WAV."""

from __future__ import annotations

import wave

from mynah.core import pipeline
from mynah.core import session as session_mod


class TestSegmentsToResult:
    def test_wraps_segments_in_result_dict(self):
        segs = [{"start": 0.0, "end": 1.0, "text": "안녕"}]
        result = pipeline.segments_to_result(segs)

        assert result["segments"] == segs
        assert result["language"] == "ko"

    def test_empty_segments(self):
        assert pipeline.segments_to_result([])["segments"] == []


class TestFinalizeSession:
    def test_writes_txt_and_wav(self, tmp_path, tmp_config_dir):
        s = session_mod.create({}, root=tmp_path)
        session_mod.append_audio(s, b"\x00\x01" * 16000)
        session_mod.append_segment(s, {"start": 0.0, "end": 1.0, "text": "첫 문장"})
        session_mod.append_segment(s, {"start": 1.0, "end": 2.0, "text": "둘째 문장"})

        result = pipeline.finalize_session(s, pipeline.PipelineOptions())

        assert result.output_path.exists()
        assert "첫 문장" in result.output_text
        assert "둘째 문장" in result.output_text
        with wave.open(str(s.dir / "meeting.wav"), "rb") as w:
            assert w.getnframes() == 16000

    def test_marks_session_done(self, tmp_path, tmp_config_dir):
        s = session_mod.create({}, root=tmp_path)
        session_mod.append_audio(s, b"\x00\x01" * 100)
        session_mod.append_segment(s, {"start": 0.0, "end": 1.0, "text": "끝"})

        pipeline.finalize_session(s, pipeline.PipelineOptions())

        assert session_mod.get_status(s) == session_mod.STATUS_DONE

    def test_timestamps_option_is_honored(self, tmp_path, tmp_config_dir):
        s = session_mod.create({}, root=tmp_path)
        session_mod.append_audio(s, b"\x00\x01" * 100)
        session_mod.append_segment(s, {"start": 65.0, "end": 66.0, "text": "타임"})

        result = pipeline.finalize_session(
            s, pipeline.PipelineOptions(timestamps=True)
        )

        assert "[00:01:05]" in result.output_text

    def test_replacements_are_applied(self, tmp_path, tmp_config_dir):
        (tmp_config_dir / "replacements.toml").write_text(
            'rule = [\n  { from = "데스", to = "defs" },\n]\n', encoding="utf-8"
        )
        s = session_mod.create({}, root=tmp_path)
        session_mod.append_audio(s, b"\x00\x01" * 100)
        session_mod.append_segment(s, {"start": 0.0, "end": 1.0, "text": "데스 일정"})

        result = pipeline.finalize_session(s, pipeline.PipelineOptions())

        assert "defs 일정" in result.output_text

    def test_transcribes_audio_no_segment_covers(self, tmp_path, tmp_config_dir, monkeypatch):
        """live_transcribe off (or a crash) leaves audio with no segments."""
        from mynah.core import live as live_mod

        calls = []

        def fake(pcm, *, start_seconds, **kw):
            calls.append((len(pcm), start_seconds))
            return {"start": start_seconds, "end": start_seconds + 10.0,
                    "text": "뒤늦게 전사됨", "retried": False, "failed": False}

        monkeypatch.setattr(live_mod, "transcribe_chunk", fake)

        s = session_mod.create({}, root=tmp_path)
        session_mod.append_audio(s, b"\x00\x01" * (16000 * 10))  # 10 s

        result = pipeline.finalize_session(s, pipeline.PipelineOptions())

        assert calls == [(320000, 0.0)]
        assert "뒤늦게 전사됨" in result.output_text

    def test_does_not_retranscribe_when_segments_cover_audio(
        self, tmp_path, tmp_config_dir, monkeypatch
    ):
        from mynah.core import live as live_mod

        def boom(*a, **kw):
            raise AssertionError("should not re-transcribe covered audio")

        monkeypatch.setattr(live_mod, "transcribe_chunk", boom)

        s = session_mod.create({}, root=tmp_path)
        session_mod.append_audio(s, b"\x00\x01" * (16000 * 10))  # 10 s
        session_mod.append_segment(s, {"start": 0.0, "end": 10.0, "text": "다 됐음"})

        result = pipeline.finalize_session(s, pipeline.PipelineOptions())

        assert "다 됐음" in result.output_text

    def test_tail_transcribe_failure_still_writes_existing_segments(
        self, tmp_path, tmp_config_dir, monkeypatch
    ):
        """A failing tail must not wedge an otherwise recoverable session."""
        from mynah.core import live as live_mod

        def boom(*a, **kw):
            raise RuntimeError("no ML stack")

        monkeypatch.setattr(live_mod, "transcribe_chunk", boom)

        s = session_mod.create({}, root=tmp_path)
        session_mod.append_audio(s, b"\x00\x01" * (16000 * 60))  # 60 s
        session_mod.append_segment(s, {"start": 0.0, "end": 10.0, "text": "앞부분은 살아남음"})

        result = pipeline.finalize_session(s, pipeline.PipelineOptions())

        assert result.output_path.exists()
        assert "앞부분은 살아남음" in result.output_text
        assert session_mod.get_status(s) == session_mod.STATUS_DONE

    def test_recovers_a_crashed_session(self, tmp_path, tmp_config_dir):
        """No clean shutdown: status still 'recording', partial JSONL line."""
        s = session_mod.create({}, root=tmp_path)
        session_mod.append_audio(s, b"\x00\x01" * 8000)
        session_mod.append_segment(s, {"start": 0.0, "end": 1.0, "text": "살아남음"})
        with s.transcript_path.open("a", encoding="utf-8") as fp:
            fp.write('{"start": 1.0, "en')

        result = pipeline.finalize_session(s, pipeline.PipelineOptions())

        assert "살아남음" in result.output_text
        assert session_mod.get_status(s) == session_mod.STATUS_DONE
