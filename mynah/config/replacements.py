"""Post-processing literal/regex replacements (~/.config/mynah/replacements.toml).

File format:

    [[rule]]
    from = "스랙"
    to = "Slack"

    [[rule]]
    from = "위스퍼"
    to = "Whisper"
    regex = false   # optional, default false (literal)
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

import tomli_w
import tomllib

from mynah.config.settings import config_dir

REPLACEMENTS_FILENAME = "replacements.toml"


@dataclass
class Rule:
    src: str
    dst: str
    regex: bool = False


def replacements_path() -> Path:
    return config_dir() / REPLACEMENTS_FILENAME


def load() -> list[Rule]:
    path = replacements_path()
    if not path.exists():
        return []
    try:
        with path.open("rb") as fp:
            data = tomllib.load(fp)
    except (tomllib.TOMLDecodeError, OSError) as exc:
        print(f"warning: could not read {path}: {exc}", file=sys.stderr)
        return []
    rules: list[Rule] = []
    for entry in data.get("rule", []):
        src = entry.get("from")
        dst = entry.get("to")
        if not isinstance(src, str) or not isinstance(dst, str) or not src:
            continue
        rules.append(Rule(src=src, dst=dst, regex=bool(entry.get("regex", False))))
    return rules


def save(rules: list[Rule]) -> Path:
    path = replacements_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "rule": [
            {"from": r.src, "to": r.dst, **({"regex": True} if r.regex else {})}
            for r in rules
            if r.src
        ]
    }
    with path.open("wb") as fp:
        tomli_w.dump(payload, fp)
    return path


def apply(text: str, rules: list[Rule]) -> str:
    for rule in rules:
        if rule.regex:
            try:
                text = re.sub(rule.src, rule.dst, text)
            except re.error as exc:
                print(
                    f"warning: invalid regex {rule.src!r} skipped: {exc}",
                    file=sys.stderr,
                )
        else:
            text = text.replace(rule.src, rule.dst)
    return text
