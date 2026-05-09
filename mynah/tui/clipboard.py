"""macOS clipboard write via the system `pbcopy` binary.

Returns False instead of raising so callers (like the result screen)
can degrade gracefully when pbcopy is missing or fails.
"""

from __future__ import annotations

import subprocess


def copy_to_clipboard(text: str) -> bool:
    """Copy `text` to the macOS clipboard. Returns True on success."""
    try:
        result = subprocess.run(
            ["pbcopy"],
            input=text.encode("utf-8"),
            check=False,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0
