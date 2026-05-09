"""Top-level entry point.

Dispatch rule:
  - No positional args and no --setup/--edit-* flag      -> launch TUI
  - Any positional arg or special flag (--setup, --help) -> CLI
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

_TUI_SUPPRESSING_FLAGS = {
    "-h",
    "--help",
    "--version",
    "--setup",
    "--doctor",
    "--edit-glossary",
    "--edit-replacements",
}


def _should_use_cli(argv: Sequence[str]) -> bool:
    """Decide between TUI and CLI based on argv (excluding the program name)."""
    for token in argv:
        if not token.startswith("-"):
            return True
        if token in _TUI_SUPPRESSING_FLAGS:
            return True
    return False


def main(argv: Sequence[str] | None = None) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]
    if _should_use_cli(args):
        from mynah.cli import run_cli
        return run_cli(args)

    # Pre-initialize the multiprocessing resource tracker BEFORE Textual starts.
    #
    # Textual replaces sys.stderr with an internal non-file object. If the
    # resource tracker first starts *inside* Textual, it calls
    # sys.stderr.fileno() which returns -1, and _posixsubprocess.fork_exec()
    # rejects -1 as "bad value(s) in fds_to_keep". Pre-initializing here
    # (while sys.stderr is still the real file) prevents that restart.
    try:
        import multiprocessing.resource_tracker as _rt
        _rt.getfd()
    except Exception:
        pass

    from mynah.tui.app import run as run_tui
    return run_tui()


if __name__ == "__main__":
    sys.exit(main())
