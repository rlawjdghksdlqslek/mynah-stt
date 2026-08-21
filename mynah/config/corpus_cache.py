from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_cache_path

CACHE_FILENAME = "corpus_cache.json"


@dataclass
class CachedCluster:
    words: list[list]   # [[word, freq], ...]
    reviewed: bool = False


def cache_path() -> Path:
    return user_cache_path("mynah") / CACHE_FILENAME


def load() -> list[CachedCluster]:
    path = cache_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"warning: could not read corpus cache: {exc}", file=sys.stderr)
        return []
    out: list[CachedCluster] = []
    for entry in data if isinstance(data, list) else []:
        try:
            out.append(CachedCluster(words=entry["words"], reviewed=entry.get("reviewed", False)))
        except (KeyError, TypeError):
            continue
    return out


def save(clusters: list[CachedCluster]) -> None:
    path = cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            [{"words": c.words, "reviewed": c.reviewed} for c in clusters],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def pending_count() -> int:
    return sum(1 for c in load() if not c.reviewed)
