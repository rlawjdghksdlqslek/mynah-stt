"""Textual App for mynah."""

from __future__ import annotations

from textual.app import App

from mynah.tui.screens.main import MainScreen
from mynah.tui.screens.replacements import ReplacementsScreen
from mynah.tui.widgets import patch_header_title_race

# Every screen composes a Header, and an unpatched one can kill the app during
# shutdown or a fast screen switch. Apply before any App is constructed.
patch_header_title_race()


class MynahApp(App):
    CSS_PATH = "app.css"
    TITLE = "mynah"
    SUB_TITLE = "local-first transcription"

    def on_mount(self) -> None:
        self.push_screen(MainScreen())


class _EditorOnlyApp(App):
    """A trimmed app that opens straight into the term manager."""

    CSS_PATH = "app.css"

    def on_mount(self) -> None:
        self.push_screen(
            ReplacementsScreen(), self._on_closed
        )

    def _on_closed(self, _result: object) -> None:
        self.exit(0)


def run() -> int:
    MynahApp().run()
    return 0


def run_editor_only() -> int:
    """Used by `mynah --edit-replacements`."""
    _EditorOnlyApp().run()
    return 0
