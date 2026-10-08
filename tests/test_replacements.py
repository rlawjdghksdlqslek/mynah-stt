"""Tests for replacement rules persistence and application."""

from __future__ import annotations

from mynah.config import replacements as r
from mynah.config.replacements import Rule


def test_load_returns_empty_when_missing(tmp_config_dir):
    assert r.load() == []


def test_save_then_load_roundtrip(tmp_config_dir):
    rules = [
        Rule(src="스랙", dst="Slack"),
        Rule(src="위스퍼", dst="Whisper"),
        Rule(src=r"\b(?:um|uh)\b", dst="", regex=True),
    ]
    r.save(rules)
    loaded = r.load()
    assert loaded == rules


def test_save_drops_empty_src(tmp_config_dir):
    r.save([Rule(src="", dst="x"), Rule(src="ok", dst="OK")])
    assert r.load() == [Rule(src="ok", dst="OK")]


def test_apply_literal():
    rules = [Rule(src="스랙", dst="Slack"), Rule(src="위스퍼", dst="Whisper")]
    text = "오늘 위스퍼로 스랙에 공유했어요."
    assert r.apply(text, rules) == "오늘 Whisper로 Slack에 공유했어요."


def test_apply_regex():
    rules = [Rule(src=r"\s+", dst=" ", regex=True)]
    assert r.apply("a   b\t\tc", rules) == "a b c"


def test_apply_invalid_regex_skipped(capsys):
    rules = [Rule(src=r"[", dst="", regex=True), Rule(src="ok", dst="OK")]
    assert r.apply("ok", rules) == "OK"
    captured = capsys.readouterr()
    assert "invalid regex" in captured.err


def test_apply_empty_rules_passthrough():
    assert r.apply("hello", []) == "hello"


class TestAsciiWordBoundaries:
    """An `ok -> OK` rule once turned "looked" into "loOKed" in real output."""

    RULES = [r.Rule(src="ok", dst="OK"), r.Rule(src="슬랙", dst="Slack")]

    def test_does_not_match_inside_an_english_word(self):
        assert r.apply("looked at the booking", self.RULES) == "looked at the booking"

    def test_matches_a_standalone_word(self):
        assert r.apply("ok, 확인했습니다", self.RULES) == "OK, 확인했습니다"

    def test_matches_when_a_korean_particle_follows(self):
        # \b is Unicode-aware and would treat 입 as a word character, killing
        # this match -- the most common shape in a Korean transcript.
        assert r.apply("ok입니다", self.RULES) == "OK입니다"

    def test_korean_rules_still_match_inside_a_word(self):
        assert r.apply("슬랙에서 얘기했어요", self.RULES) == "Slack에서 얘기했어요"
