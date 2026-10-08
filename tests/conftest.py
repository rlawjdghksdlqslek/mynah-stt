"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_config_dir(tmp_path, monkeypatch) -> Path:
    """Redirect all config/cache paths into tmp dirs for the duration of a test."""
    target = tmp_path / "config" / "mynah"
    target.mkdir(parents=True, exist_ok=True)

    from mynah.config import replacements as replacements_mod
    from mynah.config import settings as settings_mod

    monkeypatch.setattr(settings_mod, "config_dir", lambda: target)
    monkeypatch.setattr(replacements_mod, "replacements_path", lambda: target / "replacements.toml")

    return target
