"""Result screen — shown after the pipeline completes successfully.

Auto-copies the transcript to the clipboard so the user can paste straight
into Gemini/ChatGPT for meeting minutes generation, then offers buttons
for opening the file or revealing it in Finder.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static

from mynah.tui.clipboard import copy_to_clipboard


class ResultScreen(Screen):
    BINDINGS = [
        ("escape", "back", "Back"),
        ("q", "back", "Back"),
    ]

    DEFAULT_CSS = """
    ResultScreen {
        layout: vertical;
    }
    #content {
        margin: 1 2;
        padding: 1 2;
        height: auto;
    }
    #done_label {
        color: #52C41A;
        text-style: bold;
        margin-bottom: 0;
    }
    #filename {
        color: #595959;
        margin-bottom: 1;
    }
    #clip_status {
        margin-bottom: 2;
    }
    #preview {
        background: #262626;
        border: round #303030;
        padding: 1 2;
        height: auto;
        margin-bottom: 2;
        color: #8C8C8C;
    }
    #buttons {
        height: auto;
    }
    #buttons Button {
        margin-right: 2;
    }
    """

    def __init__(self, output_path: Path, output_text: str) -> None:
        super().__init__()
        self._output_path = Path(output_path)
        self._output_text = output_text

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="content"):
            yield Static("✓  Transcript saved", id="done_label")
            yield Static(self._output_path.name, id="filename")
            yield Static("", id="clip_status")
            yield Static("", id="preview")
            with Horizontal(id="buttons"):
                yield Button("New recording", id="btn_new", variant="success")
                yield Button("Open file", id="btn_open")
                yield Button("Show in Finder", id="btn_finder")
        yield Footer()

    def on_mount(self) -> None:
        ok = copy_to_clipboard(self._output_text)
        status = self.query_one("#clip_status", Static)
        if ok:
            status.update("⎘  Copied to clipboard")
            status.set_class(True, "success")
        else:
            status.update("(could not copy to clipboard)")
            status.set_class(True, "warning")

        lines = [line for line in self._output_text.splitlines() if line.strip()]
        preview = "\n".join(lines[:5])
        if len(lines) > 5:
            preview += "\n…"
        self.query_one("#preview", Static).update(preview or "(empty transcript)")

    @on(Button.Pressed, "#btn_open")
    def _on_open(self) -> None:
        subprocess.run(["open", str(self._output_path)], check=False)

    @on(Button.Pressed, "#btn_finder")
    def _on_finder(self) -> None:
        subprocess.run(["open", "-R", str(self._output_path)], check=False)

    @on(Button.Pressed, "#btn_new")
    def _on_new(self) -> None:
        # Stack: [Main, Progress, Result] → pop twice to reach Main.
        self.app.pop_screen()  # pop Result
        self.app.pop_screen()  # pop Progress

    def action_back(self) -> None:
        # Stack: [Main, Progress, Result] → pop twice to reach Main.
        self.app.pop_screen()  # pop Result
        self.app.pop_screen()  # pop Progress
