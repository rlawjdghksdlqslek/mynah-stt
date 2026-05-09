"""Main screen — minimalist record-first entry. Two paths:
  R / Space → start a new recording
  F         → open an existing audio file
Options live in the Settings screen (S key).
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.screen import Screen
from textual.widgets import DirectoryTree, Footer, Header, Label, Static


class FileBrowser(Screen):
    """Modal file picker for the 'open existing file' path."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("q", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    FileBrowser {
        align: center middle;
    }
    #browser_box {
        width: 80%;
        height: 80%;
        border: round #2DD4BF;
        padding: 1 2;
    }
    DirectoryTree {
        height: 1fr;
    }
    """

    def __init__(self, start_dir: str | None = None) -> None:
        super().__init__()
        self._start = start_dir or str(Path.home())

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="browser_box"):
            yield Label("Pick an audio file (Enter to select, Esc to cancel)")
            yield DirectoryTree(self._start)
        yield Footer()

    def on_directory_tree_file_selected(
        self, event: DirectoryTree.FileSelected
    ) -> None:
        self.dismiss(str(event.path))

    def action_cancel(self) -> None:
        self.dismiss(None)


class MainScreen(Screen):
    BINDINGS = [
        ("r", "record", "Record"),
        ("space", "record", "Record"),
        ("f", "open_file", "Open file"),
        ("s", "open_settings", "Settings"),
        ("g", "edit_glossary", "Glossary"),
        ("q", "quit", "Quit"),
    ]

    DEFAULT_CSS = """
    MainScreen {
        align: center middle;
    }
    #panel {
        width: 50;
        height: auto;
        padding: 2 4;
    }
    #record_label {
        color: #2DD4BF;
        text-style: bold;
        text-align: center;
        margin-bottom: 0;
    }
    #record_hint {
        color: #595959;
        text-align: center;
        margin-bottom: 2;
    }
    #file_label {
        color: #8C8C8C;
        text-align: center;
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="panel"):
            yield Static("●  Record", id="record_label")
            yield Static("R or Space", id="record_hint")
            yield Static("Open audio file (F)", id="file_label")
        yield Footer()

    def action_record(self) -> None:
        from mynah.tui.screens.record import RecordScreen

        self.app.push_screen(RecordScreen())

    def action_open_file(self) -> None:
        self.app.push_screen(FileBrowser(str(Path.home())), self._on_file_picked)

    def _on_file_picked(self, picked: str | None) -> None:
        if not picked:
            return
        path = Path(picked).expanduser()
        if not path.exists():
            self.notify(f"File not found: {path}", severity="error")
            return

        from mynah.config import settings as settings_mod
        from mynah.core.pipeline import PipelineOptions
        from mynah.tui.screens.progress import ProgressScreen

        settings = settings_mod.load()
        opts = PipelineOptions(
            diarize=settings.diarize,
            timestamps=settings.timestamps,
            denoise=settings.denoise,
            model=settings.model,
            language=settings.language,
            hf_token=settings.hf_token,
        )
        self.app.push_screen(ProgressScreen(path, opts))

    def action_open_settings(self) -> None:
        from mynah.tui.screens.settings import SettingsScreen

        self.app.push_screen(SettingsScreen())

    def action_edit_glossary(self) -> None:
        from mynah.tui.screens.editor import EditorScreen, EditorTarget

        self.app.push_screen(EditorScreen(EditorTarget.GLOSSARY))

    def action_quit(self) -> None:
        self.app.exit(0)
