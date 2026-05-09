"""User settings persisted to ~/.config/mynah/config.toml."""

from __future__ import annotations

import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path

import tomli_w
import tomllib
from platformdirs import user_config_path

CONFIG_DIR_NAME = "mynah"
CONFIG_FILENAME = "config.toml"


@dataclass
class Settings:
    diarize: bool = False
    timestamps: bool = False
    denoise: bool = False
    model: str = "large-v3"
    language: str = "ko"
    hf_token: str = ""

    def to_options(self) -> dict:
        return asdict(self)


def config_dir() -> Path:
    return Path(user_config_path(CONFIG_DIR_NAME, appauthor=False, ensure_exists=True))


def config_path() -> Path:
    return config_dir() / CONFIG_FILENAME


def load() -> Settings:
    path = config_path()
    if not path.exists():
        return Settings()
    try:
        with path.open("rb") as fp:
            data = tomllib.load(fp)
    except (tomllib.TOMLDecodeError, OSError) as exc:
        print(f"warning: could not read {path}: {exc}", file=sys.stderr)
        return Settings()
    valid_keys = {f.name for f in fields(Settings)}
    filtered = {k: v for k, v in data.items() if k in valid_keys}
    return Settings(**filtered)


def save(settings: Settings) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fp:
        tomli_w.dump(asdict(settings), fp)
    return path
