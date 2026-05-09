"""Tests for output formatters."""

from __future__ import annotations

from mynah.core import format as fmt


def _result(*segments) -> dict:
    return {"segments": list(segments), "language": "ko"}


def test_format_timestamp_zero_pads():
    assert fmt.format_timestamp(0) == "00:00:00"
    assert fmt.format_timestamp(59) == "00:00:59"
    assert fmt.format_timestamp(60) == "00:01:00"
    assert fmt.format_timestamp(3661) == "01:01:01"
    assert fmt.format_timestamp(3661.7) == "01:01:01"


def test_format_timestamp_negative_clamps():
    assert fmt.format_timestamp(-5) == "00:00:00"


def test_plain_strips_and_joins():
    res = _result(
        {"start": 0, "end": 1, "text": "  hello  "},
        {"start": 1, "end": 2, "text": "world"},
        {"start": 2, "end": 3, "text": "   "},  # empty after strip
    )
    assert fmt.format_plain(res) == "hello\nworld\n"


def test_plain_empty():
    assert fmt.format_plain(_result()) == ""


def test_timestamped_includes_start_seconds():
    res = _result(
        {"start": 0, "end": 1, "text": "안녕"},
        {"start": 65.4, "end": 66, "text": "여러분"},
    )
    expected = "[00:00:00] 안녕\n[00:01:05] 여러분\n"
    assert fmt.format_timestamped(res) == expected


def test_speakers_groups_consecutive_same_speaker():
    res = _result(
        {"start": 0, "end": 1, "text": "Hi", "speaker": "SPEAKER_00"},
        {"start": 1, "end": 2, "text": "there", "speaker": "SPEAKER_00"},
        {"start": 2, "end": 3, "text": "Hello", "speaker": "SPEAKER_01"},
    )
    out = fmt.format_speakers(res)
    assert out == "SPEAKER_00: Hi there\nSPEAKER_01: Hello\n"


def test_speakers_uses_unknown_when_missing():
    res = _result({"start": 0, "end": 1, "text": "no speaker"})
    out = fmt.format_speakers(res)
    assert out.startswith("UNKNOWN:")


def test_speakers_falls_back_to_word_speaker():
    res = _result(
        {
            "start": 0,
            "end": 1,
            "text": "Hi",
            "words": [{"word": "Hi", "start": 0, "end": 1, "speaker": "SPEAKER_02"}],
        }
    )
    out = fmt.format_speakers(res)
    assert out.startswith("SPEAKER_02:")


def test_speakers_timestamped_combines_both():
    res = _result(
        {"start": 0, "end": 1, "text": "Hi", "speaker": "SPEAKER_00"},
        {"start": 90, "end": 91, "text": "Bye", "speaker": "SPEAKER_01"},
    )
    out = fmt.format_speakers_timestamped(res)
    assert "[00:00:00] SPEAKER_00: Hi" in out
    assert "[00:01:30] SPEAKER_01: Bye" in out


def test_render_dispatches_correctly():
    res = _result(
        {"start": 5, "end": 6, "text": "hello", "speaker": "SPEAKER_00"},
    )
    plain = fmt.render(res, diarize=False, timestamps=False)
    ts = fmt.render(res, diarize=False, timestamps=True)
    sp = fmt.render(res, diarize=True, timestamps=False)
    both = fmt.render(res, diarize=True, timestamps=True)

    assert plain.strip() == "hello"
    assert ts.strip().startswith("[00:00:05] hello")
    assert sp.strip().startswith("SPEAKER_00: hello")
    assert both.strip().startswith("[00:00:05] SPEAKER_00: hello")
