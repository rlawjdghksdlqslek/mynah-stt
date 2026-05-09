"""Textual App for mynah."""

from __future__ import annotations

from textual.app import App

from mynah.tui.screens.editor import EditorScreen, EditorTarget
from mynah.tui.screens.main import MainScreen


class MynahApp(App):
    CSS_PATH = "app.css"
    TITLE = "mynah"
    SUB_TITLE = "local-first transcription"

    def on_mount(self) -> None:
        self.push_screen(MainScreen())


class _EditorOnlyApp(App):
    """A trimmed app that opens straight into an editor screen."""

    def __init__(self, target: EditorTarget):
        super().__init__()
        self._target = target

    def on_mount(self) -> None:
        self.push_screen(EditorScreen(self._target), self._on_closed)

    def _on_closed(self, _result: object) -> None:
        self.exit(0)


def run() -> int:
    MynahApp().run()
    return 0


def run_editor_only(target: str) -> int:
    """Used by `mynah --edit-glossary` and `mynah --edit-replacements`."""
    et = EditorTarget(target)
    _EditorOnlyApp(et).run()
    return 0
