"""Tests for settings persistence."""

from __future__ import annotations

from mynah.config import settings as s


def test_defaults():
    settings = s.Settings()
    assert settings.diarize is False
    assert settings.timestamps is False
    assert settings.denoise is False
    assert settings.model == "large-v3"
    assert settings.language == "ko"
    assert settings.hf_token == ""


def test_load_returns_defaults_when_missing(tmp_config_dir):
    settings = s.load()
    assert settings == s.Settings()


def test_save_then_load_roundtrip(tmp_config_dir):
    original = s.Settings(
        diarize=True,
        timestamps=True,
        denoise=False,
        model="large-v3-turbo",
        language="en",
        hf_token="hf_xxx",
    )
    s.save(original)
    loaded = s.load()
    assert loaded == original


def test_load_ignores_unknown_keys(tmp_config_dir):
    path = s.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        'diarize = true\nmodel = "large-v3"\nfuture_field = "unused"\n',
        encoding="utf-8",
    )
    settings = s.load()
    assert settings.diarize is True
    assert settings.model == "large-v3"


def test_load_corrupt_file_returns_defaults(tmp_config_dir, capsys):
    path = s.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("this is :: not valid toml ===", encoding="utf-8")
    settings = s.load()
    assert settings == s.Settings()
    err = capsys.readouterr().err
    assert "could not read" in err


def test_to_options_dict():
    settings = s.Settings(diarize=True, model="turbo")
    opts = settings.to_options()
    assert opts["diarize"] is True
    assert opts["model"] == "turbo"
    assert "hf_token" in opts
