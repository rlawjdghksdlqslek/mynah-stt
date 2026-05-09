"""Tests for glossary persistence and prompt formatting."""

from __future__ import annotations

from mynah.config import glossary as g


def test_load_returns_empty_when_missing(tmp_config_dir):
    assert g.load() == []


def test_save_then_load_preserves_order_and_dedupes(tmp_config_dir):
    g.save(["Whisper", "Slack", "Whisper", "  ", "pyannote"])
    assert g.load() == ["Whisper", "Slack", "pyannote"]


def test_load_skips_blank_and_comment_lines(tmp_config_dir):
    path = g.glossary_path()
    path.write_text(
        "# project glossary\n"
        "Whisper\n"
        "\n"
        "  Slack  \n"
        "# comment\n"
        "pyannote\n",
        encoding="utf-8",
    )
    assert g.load() == ["Whisper", "Slack", "pyannote"]


def test_as_initial_prompt_empty():
    assert g.as_initial_prompt([]) == ""


def test_as_initial_prompt_format():
    out = g.as_initial_prompt(["Whisper", "Slack", "pyannote"])
    assert out.startswith("Glossary of proper nouns")
    assert "Whisper" in out
    assert "Slack" in out
    assert "pyannote" in out
    assert out.endswith(".")


def test_as_hotwords_joins_with_spaces():
    assert g.as_hotwords(["Whisper", "Slack"]) == "Whisper Slack"
    assert g.as_hotwords([]) == ""
