"""Main screen — minimalist record-first entry. Two paths:
  R / Space → start a new recording
  F         → open an existing audio file
Options live in the Settings screen (S key).
Term management lives in TermManagerScreen (G / T key).
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.screen import Screen
from textual.widgets import Button, DirectoryTree, Footer, Header, Label, Static

from mynah.core.audio import SUPPORTED_INPUT_EXTS


class AudioTree(DirectoryTree):
    def filter_paths(self, paths):
        return [
            p for p in paths
            if not p.name.startswith(".")
            and (p.is_dir() or p.suffix.lower() in SUPPORTED_INPUT_EXTS)
        ]


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
            # AudioTree hides everything ffmpeg cannot decode.
            yield AudioTree(self._start)
        yield Footer()

    def on_directory_tree_file_selected(
        self, event: DirectoryTree.FileSelected
    ) -> None:
        self.dismiss(str(event.path))

    def action_cancel(self) -> None:
        self.dismiss(None)


class RecoveryScreen(Screen):
    """Three choices for an unfinished session. Nothing is deleted until the
    user picks 'discard'."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    DEFAULT_CSS = """
    RecoveryScreen { align: center middle; }
    #recovery_box {
        width: 60; height: auto; padding: 2 4; border: round $error;
    }
    #recovery_box Button { width: 100%; margin-top: 1; }
    """

    def __init__(self, session) -> None:
        super().__init__()
        self._session = session
        self._confirm_discard = False

    def compose(self) -> ComposeResult:
        from mynah.core import session as session_mod

        mins = int(session_mod.duration_seconds(self._session) / 60)
        segs = len(session_mod.read_segments(self._session))
        with Container(id="recovery_box"):
            yield Label(f"Unfinished session: {self._session.dir.name}")
            yield Label(f"{mins} min recorded · {segs} chunks transcribed")
            yield Button("Finish and transcribe", id="btn_finish", variant="success")
            yield Button("Resume recording", id="btn_resume")
            yield Button("Discard", id="btn_discard", variant="error")

    def on_button_pressed(self, event) -> None:
        if event.button.id == "btn_discard" and not self._confirm_discard:
            # Deleting a session destroys the only copy of a recording.
            # Make the user say it twice.
            self._confirm_discard = True
            event.button.label = "Press again to delete for good"
            return
        self.dismiss(
            {
                "btn_finish": "finish",
                "btn_resume": "resume",
                "btn_discard": "discard",
            }[event.button.id]
        )

    def action_cancel(self) -> None:
        self.dismiss(None)


class MainScreen(Screen):
    BINDINGS = [
        ("r", "record", "Record"),
        ("space", "record", "Record"),
        ("f", "open_file", "Open file"),
        ("s", "open_settings", "Settings"),
        ("g", "open_terms", "Terms"),
        Binding("t", "open_analyze", "Review terms", show=False),
        ("o", "open_folder", "Recordings"),
        Binding("u", "resume_session", "Unfinished", show=False),
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
        color: #8C8C8C;
        text-align: center;
        margin-bottom: 2;
    }
    #file_label {
        color: #D9D9D9;
        text-align: center;
        margin-top: 1;
    }
    #review_badge {
        color: $warning;
        text-align: center;
        margin-top: 1;
    }
    #unfinished_badge {
        color: $error;
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
            yield Static("", id="review_badge")
            yield Static("", id="unfinished_badge")
        yield Footer()

    def on_mount(self) -> None:
        self._update_badge()

    def on_screen_resume(self) -> None:
        self._update_badge()

    def _update_badge(self) -> None:
        from mynah.config import corpus_cache
        count = corpus_cache.pending_count()
        badge = self.query_one("#review_badge", Static)
        if count > 0:
            badge.update(f"Review terms · {count}  (T)")
        else:
            badge.update("")

        from mynah.core import session as session_mod

        pending = session_mod.list_unfinished()
        unfinished = self.query_one("#unfinished_badge", Static)
        if pending:
            mins = int(session_mod.duration_seconds(pending[-1]) / 60)
            extra = f" (+{len(pending) - 1} more)" if len(pending) > 1 else ""
            unfinished.update(f"Unfinished session · {mins} min recorded{extra}  (U)")
        else:
            unfinished.update("")

    def on_click(self, event) -> None:
        action = {
            "record_label": self.action_record,
            "record_hint": self.action_record,
            "file_label": self.action_open_file,
            "review_badge": self.action_open_analyze,
            "unfinished_badge": self.action_resume_session,
        }.get(getattr(event.widget, "id", None))
        if action is not None:
            action()

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
        self.app.push_screen(ProgressScreen(audio_path=path, options=opts))

    def action_resume_session(self) -> None:
        from mynah.core import session as session_mod

        pending = session_mod.list_unfinished()
        if not pending:
            self.notify("No unfinished sessions")
            return
        target = pending[-1]
        self.app.push_screen(
            RecoveryScreen(target),
            lambda choice: self._on_recovery_choice(choice, target),
        )

    def _on_recovery_choice(self, choice: str | None, target) -> None:
        if not choice:
            return

        if choice == "discard":
            import shutil

            try:
                shutil.rmtree(target.dir)
            except OSError as exc:
                self.notify(f"Could not delete: {exc}", severity="error")
            self._update_badge()
            return

        from mynah.config import settings as settings_mod
        from mynah.core.pipeline import PipelineOptions

        settings = settings_mod.load()
        opts = PipelineOptions(
            diarize=settings.diarize,
            timestamps=settings.timestamps,
            denoise=settings.denoise,
            model=settings.model,
            language=settings.language,
            hf_token=settings.hf_token,
        )
        if choice == "finish":
            from mynah.tui.screens.progress import ProgressScreen
            self.app.push_screen(ProgressScreen(session=target, options=opts))
        elif choice == "resume":
            from mynah.tui.screens.record import RecordScreen
            self.app.push_screen(RecordScreen(session=target))

    def action_open_settings(self) -> None:
        from mynah.tui.screens.settings import SettingsScreen
        self.app.push_screen(SettingsScreen())

    def action_open_terms(self) -> None:
        from mynah.tui.screens.term_manager import TermManagerScreen
        self.app.push_screen(TermManagerScreen(initial_tab="glossary"))

    def action_open_analyze(self) -> None:
        from mynah.tui.screens.term_manager import TermManagerScreen
        self.app.push_screen(TermManagerScreen(initial_tab="analyze"))

    def action_open_folder(self) -> None:
        import subprocess

        from mynah.core import session as session_mod

        root = session_mod.default_root()
        root.mkdir(parents=True, exist_ok=True)
        subprocess.run(["open", str(root)], check=False)

    def action_quit(self) -> None:
        self.app.exit(0)
