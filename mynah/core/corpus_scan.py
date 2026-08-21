from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from kiwipiepy import Kiwi

_KEEP_TAGS = {"NNG", "NNP", "SL"}


@lru_cache(maxsize=1)
def _get_kiwi() -> Kiwi:
    return Kiwi()


def scan_transcripts(dirs: list[Path]) -> dict[str, int]:
    """Count noun/foreign-word frequencies across all .txt files in the given dirs."""
    freq: dict[str, int] = {}
    seen: set[Path] = set()
    for d in dirs:
        d = Path(d).expanduser().resolve()
        if not d.is_dir():
            continue
        for txt in sorted(d.glob("*.txt")):
            resolved = txt.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                text = txt.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                print(f"warning: skipping {txt}: {exc}", file=sys.stderr)
                continue
            for token in _get_kiwi().tokenize(text):
                if token.tag in _KEEP_TAGS and len(token.form) >= 2:
                    freq[token.form] = freq.get(token.form, 0) + 1
    return freq
