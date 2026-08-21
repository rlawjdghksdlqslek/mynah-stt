"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_config_dir(tmp_path, monkeypatch) -> Path:
    """Redirect all config/cache paths into tmp dirs for the duration of a test."""
    target = tmp_path / "config" / "mynah"
    target.mkdir(parents=True, exist_ok=True)

    from mynah.config import corpus_cache as corpus_cache_mod
    from mynah.config import glossary as glossary_mod
    from mynah.config import replacements as replacements_mod
    from mynah.config import settings as settings_mod

    monkeypatch.setattr(settings_mod, "config_dir", lambda: target)
    monkeypatch.setattr(glossary_mod, "glossary_path", lambda: target / "glossary.txt")
    monkeypatch.setattr(replacements_mod, "replacements_path", lambda: target / "replacements.toml")

    cache_target = tmp_path / "cache" / "mynah"
    cache_target.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(corpus_cache_mod, "cache_path", lambda: cache_target / "corpus_cache.json")

    return target
