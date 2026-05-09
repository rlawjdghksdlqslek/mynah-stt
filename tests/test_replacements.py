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
