"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_config_dir(tmp_path, monkeypatch) -> Path:
    """Redirect ~/.config/mynah into a tmp dir for the duration of a test.

    `platformdirs` honors the XDG_CONFIG_HOME env var on macOS/Linux.
    """
    cfg_root = tmp_path / "config"
    cfg_root.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(cfg_root))
    # On macOS, platformdirs reads ~/Library/Application Support by default;
    # XDG_CONFIG_HOME overrides only when that path resolves through it.
    # Patch the resolver to be safe.
    from mynah.config import settings as settings_mod

    target = cfg_root / "mynah"
    target.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings_mod, "config_dir", lambda: target)
    return target
