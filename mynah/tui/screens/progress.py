"""Progress screen — runs the pipeline in a worker thread and shows live status."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Log, ProgressBar, Static

from mynah.core.pipeline import PipelineOptions, PipelineResult
from mynah.core.pipeline import run as run_pipeline


@dataclass
class StageState:
    name: str
    label: str
    status: str = "waiting"  # waiting / running / done / failed / skipped
    progress: float = 0.0


STAGES = [
    ("audio",      "Audio normalize"),
    ("denoise",    "Denoise  (optional)"),
    ("transcribe", "Whisper transcribe"),
    ("diarize",    "Speaker diarization  (optional)"),
    ("format",     "Format and save"),
]


class ProgressScreen(Screen):
    BINDINGS = [
        ("q", "back_or_cancel", "Back / Cancel"),
        ("escape", "back_or_cancel", "Back / Cancel"),
    ]

    DEFAULT_CSS = """
    ProgressScreen {
        layout: vertical;
    }
    #content {
        margin: 1 2;
        padding: 1 2;
        height: auto;
    }
    .file_label {
        color: #2DD4BF;
        text-style: bold;
        margin-bottom: 2;
    }
    .stage_row {
        height: 1;
        margin-bottom: 0;
    }
    #bar {
        margin-top: 1;
        margin-bottom: 1;
    }
    #log {
        height: 10;
        margin-top: 1;
        border: round $primary;
    }
    #buttons {
        height: auto;
        margin-top: 1;
        align-horizontal: right;
    }
    #buttons Button {
        margin-left: 2;
    }
    """

    def __init__(self, audio_path: Path, options: PipelineOptions):
        super().__init__()
        self._audio_path = audio_path
        self._options = options
        self._stages: dict[str, StageState] = {
            name: StageState(name=name, label=label) for name, label in STAGES
        }
        if not options.denoise:
            self._stages["denoise"].status = "skipped"
        if not options.diarize:
            self._stages["diarize"].status = "skipped"
        self._result: PipelineResult | None = None
        self._error: BaseException | None = None
        self._done = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="content"):
            yield Static(f"Transcribing: {self._audio_path.name}", classes="file_label")
            for name, _ in STAGES:
                yield Static(self._render_stage_line(name), id=f"row_{name}", markup=True)
            yield ProgressBar(total=100, show_eta=False, id="bar")
            yield Log(id="log", highlight=False)
            with Vertical(id="buttons"):
                yield Button("Back", id="btn_back", disabled=True)
        yield Footer()

    def on_mount(self) -> None:
        from mynah.core.model_cache import is_whisper_cached

        if not is_whisper_cached(self._options.model):
            self._log(
                "First run: downloading Whisper model "
                "(~3 GB, 5-15 min on broadband)..."
            )
            self._log("Subsequent runs use the cached model and start instantly.")
        self._log("Starting pipeline...")
        self.run_worker(self._do_run, thread=True, exclusive=True)

    def _render_stage_line(self, name: str) -> str:
        s = self._stages[name]
        icons = {
            "waiting":  ("○", "#595959"),
            "running":  ("▶", "#2DD4BF"),
            "done":     ("✓", "#52C41A"),
            "failed":   ("✗", "#FF4D4F"),
            "skipped":  ("—", "#595959"),
        }
        status_colors = {
            "waiting":  "#595959",
            "running":  "#2DD4BF",
            "done":     "#52C41A",
            "failed":   "#FF4D4F",
            "skipped":  "#595959",
        }
        icon, icon_color = icons.get(s.status, ("○", "#595959"))
        status_color = status_colors.get(s.status, "#595959")
        label = s.label
        return (
            f"  [{icon_color}]{icon}[/{icon_color}]  "
            f"{label:<36}  "
            f"[{status_color}]{s.status}[/{status_color}]"
        )

    def _refresh_stage(self, name: str) -> None:
        widget = self.query_one(f"#row_{name}", Static)
        widget.update(self._render_stage_line(name))

    def _log(self, message: str) -> None:
        try:
            self.query_one("#log", Log).write_line(message)
        except Exception:
            pass

    def _do_run(self) -> None:
        def progress_cb(stage: str, message: str, p: float | None) -> None:
            self.app.call_from_thread(self._on_progress, stage, message, p)

        try:
            result = run_pipeline(
                self._audio_path, self._options, on_progress=progress_cb
            )
        except BaseException as exc:  # noqa: BLE001 — surface anything
            self._error = exc
            self.app.call_from_thread(self._on_finished)
            return
        self._result = result
        self.app.call_from_thread(self._on_finished)

    def _on_progress(self, stage: str, message: str, p: float | None) -> None:
        s = self._stages.get(stage)
        if s is None:
            self._log(f"[{stage}] {message}")
            return
        s.status = "running"
        if p is not None:
            s.progress = p
            try:
                self.query_one("#bar", ProgressBar).update(progress=int(p * 100))
            except Exception:
                pass
        self._refresh_stage(stage)
        self._log(f"[{stage}] {message}")

    def _on_finished(self) -> None:
        self._done = True
        if self._error is not None:
            for name in self._stages:
                if self._stages[name].status == "running":
                    self._stages[name].status = "failed"
                    self._refresh_stage(name)
            self._log(f"ERROR: {self._error}")
            try:
                self.query_one("#btn_back", Button).disabled = False
            except Exception:
                pass
            return

        for name in self._stages:
            if self._stages[name].status == "running":
                self._stages[name].status = "done"
                self._refresh_stage(name)
        assert self._result is not None
        self._log(f"Wrote {self._result.output_path}")
        try:
            self.query_one("#bar", ProgressBar).update(progress=100)
        except Exception:
            pass

        # Hand off to result screen (push, not switch, so Main stays in stack).
        from mynah.tui.screens.result import ResultScreen

        self.app.push_screen(
            ResultScreen(self._result.output_path, self._result.output_text)
        )

    @on(Button.Pressed, "#btn_back")
    def _on_back(self) -> None:
        self.app.pop_screen()

    def action_back_or_cancel(self) -> None:
        if self._done:
            self.app.pop_screen()
        else:
            self._log("Cancellation requested — finishing current stage...")
