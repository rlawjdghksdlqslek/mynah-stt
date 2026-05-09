"""Glossary file management (~/.config/mynah/glossary.txt)."""

from __future__ import annotations

import sys
from pathlib import Path

from mynah.config.settings import config_dir

GLOSSARY_FILENAME = "glossary.txt"


def glossary_path() -> Path:
    return config_dir() / GLOSSARY_FILENAME


def load() -> list[str]:
    path = glossary_path()
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"warning: could not read {path}: {exc}", file=sys.stderr)
        return []
    seen: set[str] = set()
    out: list[str] = []
    for line in raw.splitlines():
        term = line.strip()
        if not term or term.startswith("#"):
            continue
        if term in seen:
            continue
        seen.add(term)
        out.append(term)
    return out


def save(terms: list[str]) -> Path:
    path = glossary_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    cleaned: list[str] = []
    for term in terms:
        t = term.strip()
        if not t or t in seen:
            continue
        seen.add(t)
        cleaned.append(t)
    path.write_text("\n".join(cleaned) + ("\n" if cleaned else ""), encoding="utf-8")
    return path


def as_initial_prompt(terms: list[str]) -> str:
    """Build a Whisper initial_prompt that biases the model toward these terms.

    Whisper's initial_prompt has a 224-token cap; we keep it short by listing
    terms separated by commas. The phrasing primes the model that these are
    proper nouns expected in the audio.
    """
    if not terms:
        return ""
    return "Glossary of proper nouns and terms used: " + ", ".join(terms) + "."


def as_hotwords(terms: list[str]) -> str:
    """faster-whisper hotwords parameter expects a single string."""
    return " ".join(terms)
