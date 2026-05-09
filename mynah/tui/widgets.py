"""Reusable Textual widgets for mynah."""

from __future__ import annotations

from textual.widgets import Static


class StatusLine(Static):
    """A single-line status message at the bottom of a screen."""

    DEFAULT_CSS = """
    StatusLine {
        dock: bottom;
        height: 1;
        background: $boost;
        color: $text;
        padding: 0 1;
    }
    """

    def set_status(self, message: str) -> None:
        self.update(message)
