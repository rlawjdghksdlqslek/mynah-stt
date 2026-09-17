"""Hallucination-loop detection. No model needed."""

from __future__ import annotations

import threading

from mynah.core import live
from mynah.core import session as session_mod


class TestWorstRepeat:
    def test_no_repetition(self):
        assert live.worst_repeat("가 나 다 라".split(), 1) == 1

    def test_counts_consecutive_unigrams(self):
        assert live.worst_repeat("네 네 네 네 다음".split(), 1) == 4

    def test_counts_consecutive_ngrams(self):
        toks = "가 나 다 " * 3
        assert live.worst_repeat(toks.split(), 3) == 3

    def test_ignores_non_consecutive_repeats(self):
        assert live.worst_repeat("가 나 가 나 다".split(), 1) == 1

    def test_empty_input(self):
        assert live.worst_repeat([], 6) == 0


class TestHasLoop:
    def test_clean_korean_text_is_not_a_loop(self):
        text = "그래서 이번 스프린트는 다음 주까지 진행하고 배포는 그 다음 주에 하겠습니다."
        assert live.has_loop(text) is False

    def test_crystal_loop_is_detected(self):
        # The literal failure observed in this project's own recordings
        assert live.has_loop("네 안 " + "Crystal " * 219) is True

    def test_korean_filler_loop_is_detected(self):
        assert live.has_loop("아 " * 12) is True

    def test_phrase_loop_is_detected(self):
        assert live.has_loop("10만원, 그래서 이제 저희가 " * 4) is True

    def test_short_backchannel_is_not_a_loop(self):
        # Three "네" in a row is normal Korean conversation, not a hallucination
        assert live.has_loop("네 네 네 그러면 다음으로 넘어가겠습니다") is False

    def test_empty_text(self):
        assert live.has_loop("") is False

    def test_briefly_repeated_real_speech_is_not_a_loop(self):
        # Ordinary Korean: "a bit more, a bit more, a bit more, to the left".
        # A 2-gram x3 is only 6 tokens; flagging it would delete the whole
        # chunk in the worker's retry path.
        assert live.has_loop("조금 더 조금 더 조금 더 왼쪽으로") is False


class TestMarkGap:
    def test_gap_marker_contains_timestamps(self):
        marker = live.mark_gap(65.0, 125.0)
        assert "01:05" in marker
        assert "02:05" in marker

    def test_gap_marker_is_recognizable(self):
        assert "[" in live.mark_gap(0.0, 1.0)


class FakeRecorder:
    """Feeds a scripted list of chunk ranges, then stops."""

    def __init__(self, ranges):
        self._ranges = list(ranges)
        self.final = None

    def pop_ready_chunk(self):
        return self._ranges.pop(0) if self._ranges else None

    def flush_final_chunk(self):
        return self.final


def _fake_transcribe(text_by_call):
    calls = {"n": 0, "prompts": [], "backends": []}

    def fn(pcm, *, model_name, language, initial_prompt, backend, beam_size=None):
        calls["prompts"].append(initial_prompt)
        calls["backends"].append(backend)
        i = min(calls["n"], len(text_by_call) - 1)
        calls["n"] += 1
        return {"segments": [], "language": language, "text": text_by_call[i]}

    return fn, calls


class TestTranscribeChunk:
    def test_offsets_timestamps_to_meeting_time(self):
        fn, _ = _fake_transcribe(["안녕하세요"])
        seg = live.transcribe_chunk(
            b"\x00" * 3200, start_seconds=60.0, model_name="large-v3",
            language="ko", prompt="", backend="mlx", transcribe_fn=fn,
        )
        assert seg["start"] == 60.0
        assert abs(seg["end"] - 60.1) < 0.001
        assert seg["text"] == "안녕하세요"
        assert seg["retried"] is False

    def test_loop_triggers_whisperx_retry(self):
        fn, calls = _fake_transcribe(["Crystal " * 30, "정상 문장입니다"])
        seg = live.transcribe_chunk(
            b"\x00" * 3200, start_seconds=0.0, model_name="large-v3",
            language="ko", prompt="", backend="mlx", transcribe_fn=fn,
        )
        assert seg["retried"] is True
        assert seg["failed"] is False
        assert seg["text"] == "정상 문장입니다"
        assert calls["backends"] == ["mlx", "whisperx"]

    def test_loop_surviving_retry_becomes_a_gap(self):
        fn, _ = _fake_transcribe(["Crystal " * 30])
        seg = live.transcribe_chunk(
            b"\x00" * 3200, start_seconds=0.0, model_name="large-v3",
            language="ko", prompt="", backend="mlx", transcribe_fn=fn,
        )
        assert seg["failed"] is True
        assert "transcription failed" in seg["text"]


class TestRunWorker:
    def test_appends_one_segment_per_chunk(self, tmp_path):
        s = session_mod.create({}, root=tmp_path)
        session_mod.append_audio(s, b"\x01\x00" * 8000)

        rec = FakeRecorder([(0, 3200, False), (3200, 6400, False)])
        fn, _ = _fake_transcribe(["첫 번째", "두 번째"])
        stop = threading.Event()
        stop.set()  # exit after draining what is already queued

        live.run_worker(
            s, rec, model_name="large-v3", language="ko", glossary="",
            backend="mlx", transcribe_fn=fn, sleep_fn=lambda _s: None,
            stop_event=stop,
        )

        segs = session_mod.read_segments(s)
        assert [x["text"] for x in segs] == ["첫 번째", "두 번째"]

    def test_passes_previous_text_as_context(self, tmp_path):
        s = session_mod.create({}, root=tmp_path)
        session_mod.append_audio(s, b"\x01\x00" * 8000)

        rec = FakeRecorder([(0, 3200, False), (3200, 6400, False)])
        fn, calls = _fake_transcribe(["앞 청크 마지막 문장", "뒤 청크"])
        stop = threading.Event()
        stop.set()

        live.run_worker(
            s, rec, model_name="large-v3", language="ko", glossary="용어집",
            backend="mlx", transcribe_fn=fn, sleep_fn=lambda _s: None,
            stop_event=stop,
        )

        assert calls["prompts"][0] == "용어집"
        assert "앞 청크 마지막 문장" in calls["prompts"][1]
        assert calls["prompts"][1].startswith("용어집")

    def test_notifies_on_each_segment(self, tmp_path):
        s = session_mod.create({}, root=tmp_path)
        session_mod.append_audio(s, b"\x01\x00" * 8000)

        seen = []
        rec = FakeRecorder([(0, 3200, False)])
        fn, _ = _fake_transcribe(["보고"])
        stop = threading.Event()
        stop.set()

        live.run_worker(
            s, rec, model_name="large-v3", language="ko", glossary="",
            backend="mlx", transcribe_fn=fn, sleep_fn=lambda _s: None,
            stop_event=stop, on_segment=seen.append,
        )

        assert [x["text"] for x in seen] == ["보고"]

    def test_transcribes_final_chunk_after_stop(self, tmp_path):
        s = session_mod.create({}, root=tmp_path)
        session_mod.append_audio(s, b"\x01\x00" * 8000)

        rec = FakeRecorder([])
        rec.final = (0, 3200, False)
        fn, _ = _fake_transcribe(["마지막"])
        stop = threading.Event()
        stop.set()

        live.run_worker(
            s, rec, model_name="large-v3", language="ko", glossary="",
            backend="mlx", transcribe_fn=fn, sleep_fn=lambda _s: None,
            stop_event=stop,
        )

        assert [x["text"] for x in session_mod.read_segments(s)] == ["마지막"]

    def test_retry_storm_stops_retrying(self, tmp_path):
        """Bad mic: every chunk loops. Retrying each one is 12x slower than the
        fast path, so the queue would grow without bound."""
        s = session_mod.create({}, root=tmp_path)
        session_mod.append_audio(s, b"\x01\x00" * 40000)

        ranges = [(i * 3200, (i + 1) * 3200, False) for i in range(6)]
        rec = FakeRecorder(ranges)
        fn, calls = _fake_transcribe(["Crystal " * 30])
        stop = threading.Event()
        stop.set()

        live.run_worker(
            s, rec, model_name="large-v3", language="ko", glossary="",
            backend="mlx", transcribe_fn=fn, sleep_fn=lambda _s: None,
            stop_event=stop,
        )

        # 3 chunks retried (mlx+whisperx = 2 calls each), then retries stop
        # and later chunks cost one call each.
        assert calls["backends"].count("whisperx") == live.MAX_CONSECUTIVE_RETRIES
        assert all("transcription failed" in x["text"] for x in session_mod.read_segments(s))

    def test_worker_survives_a_raising_transcribe_fn(self, tmp_path):
        s = session_mod.create({}, root=tmp_path)
        session_mod.append_audio(s, b"\x01\x00" * 8000)

        calls = {"n": 0}

        def exploding(pcm, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("GPU busy")
            return {"segments": [], "language": "ko", "text": "그 다음 청크"}

        rec = FakeRecorder([(0, 3200, False), (3200, 6400, False)])
        stop = threading.Event()
        stop.set()

        live.run_worker(
            s, rec, model_name="large-v3", language="ko", glossary="",
            backend="mlx", transcribe_fn=exploding, sleep_fn=lambda _s: None,
            stop_event=stop,
        )

        segs = session_mod.read_segments(s)
        # The bad chunk becomes a gap; the worker keeps going.
        assert len(segs) == 2
        assert "transcription failed" in segs[0]["text"]
        assert segs[1]["text"] == "그 다음 청크"

    def test_failed_chunk_does_not_poison_next_context(self, tmp_path):
        s = session_mod.create({}, root=tmp_path)
        session_mod.append_audio(s, b"\x01\x00" * 8000)

        rec = FakeRecorder([(0, 3200, False), (3200, 6400, False)])
        fn, calls = _fake_transcribe(["Crystal " * 40, "정상 문장"])
        stop = threading.Event()
        stop.set()

        live.run_worker(
            s, rec, model_name="large-v3", language="ko", glossary="용어집",
            backend="mlx", transcribe_fn=fn, sleep_fn=lambda _s: None,
            stop_event=stop,
        )

        # The gap marker must never be handed to the next chunk as context.
        assert all("transcription failed" not in p for p in calls["prompts"])

    def test_segment_timestamps_are_meeting_relative(self, tmp_path):
        s = session_mod.create({}, root=tmp_path)
        session_mod.append_audio(s, b"\x01\x00" * 100000)

        rec = FakeRecorder([(32000, 64000, False)])
        fn, _ = _fake_transcribe(["1분 지점"])
        stop = threading.Event()
        stop.set()

        live.run_worker(
            s, rec, model_name="large-v3", language="ko", glossary="",
            backend="mlx", transcribe_fn=fn, sleep_fn=lambda _s: None,
            stop_event=stop,
        )

        seg = session_mod.read_segments(s)[0]
        assert seg["start"] == 1.0
        assert abs(seg["end"] - 2.0) < 0.001


class TestGuardSegments:
    def test_replaces_only_the_looping_segment(self):
        segs = [
            {"start": 0.0, "end": 5.0, "text": "정상적인 회의 발언입니다"},
            {"start": 5.0, "end": 9.0, "text": "Crystal " * 20},
        ]
        live.guard_segments(segs)
        assert segs[0]["text"] == "정상적인 회의 발언입니다"
        assert "transcription failed" in segs[1]["text"]
        assert "00:00:05-00:00:09" in segs[1]["text"]

    def test_empty_list_is_fine(self):
        assert live.guard_segments([]) == []
