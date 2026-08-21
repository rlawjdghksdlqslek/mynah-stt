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


def patch_header_title_race() -> None:
    """Stop Textual's Header from crashing the app on shutdown.

    `Header._on_mount` registers watchers whose callback runs
    `query_one(HeaderTitle)`. The callback is a coroutine, so it runs a beat
    later — and if the header's children are already unmounted by then (app
    shutting down, screens switching quickly), the query raises `NoMatches`.
    Upstream catches `NoScreen` but not `NoMatches`, so it escapes and takes
    the whole app down. See Textualize/textual#4817 and discussion #4268;
    still unfixed as of textual 8.2.5.

    This cost a real recording: the crash landed between `finalize_wav()` and
    the transcript write, leaving a 24-minute meeting stuck at status
    "transcribing" with no `meeting.txt`.

    Subclassing does not work — Textual dispatches `_on_mount` to every class
    in the MRO, so the parent's buggy closure gets registered too. The class
    attribute itself has to be replaced. Idempotent; safe to call more than
    once.
    """
    from textual.css.query import NoMatches
    from textual.dom import NoScreen
    from textual.widgets import Header
    from textual.widgets._header import HeaderTitle

    if getattr(Header._on_mount, "_mynah_patched", False):
        return

    def _on_mount(self, _event) -> None:
        async def set_title() -> None:
            try:
                self.query_one(HeaderTitle).update(self.format_title())
            except (NoMatches, NoScreen):
                pass

        self.watch(self.app, "title", set_title)
        self.watch(self.app, "sub_title", set_title)
        self.watch(self.screen, "title", set_title)
        self.watch(self.screen, "sub_title", set_title)

    # ponytail: monkeypatch, because the bug is a third-party one-liner.
    # Delete this whole function once textual ships the NoMatches catch.
    _on_mount._mynah_patched = True
    Header._on_mount = _on_mount
