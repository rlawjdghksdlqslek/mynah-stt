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
        ("q", "back", "Back"),
        ("escape", "back", "Back"),
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

    def __init__(
        self,
        session=None,
        options: PipelineOptions | None = None,
        audio_path: Path | None = None,
    ):
        super().__init__()
        if (session is None) == (audio_path is None):
            raise ValueError("pass exactly one of session= or audio_path=")
        self._session = session
        self._audio_path = audio_path
        self._options = options or PipelineOptions()
        self._stages: dict[str, StageState] = {
            name: StageState(name=name, label=label) for name, label in STAGES
        }
        if session is not None:
            # Live chunk transcription already happened during recording.
            for skipped in ("audio", "denoise", "transcribe"):
                self._stages[skipped].status = "skipped"
        elif not self._options.denoise:
            self._stages["denoise"].status = "skipped"
        if not self._options.diarize:
            self._stages["diarize"].status = "skipped"
        self._label_name = session.dir.name if session else audio_path.name
        self._elapsed = 0
        self._clock = None
        self._result: PipelineResult | None = None
        self._error: BaseException | None = None
        self._done = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="content"):
            yield Static(
                f"Processing: {self._label_name}", id="file_label", classes="file_label"
            )
            for name, _ in STAGES:
                yield Static(self._render_stage_line(name), id=f"row_{name}", markup=True)
            yield ProgressBar(total=100, show_eta=False, id="bar")
            yield Log(id="log", highlight=False)
            with Vertical(id="buttons"):
                yield Button("Back", id="btn_back", disabled=True)
        yield Footer()

    def on_mount(self) -> None:
        from mynah.config import settings as settings_mod
        from mynah.core.model_cache import is_whisper_cached
        from mynah.core.pipeline import has_uncovered_audio
        from mynah.core.transcribe import pick_backend

        # A session only skips Whisper when diarize is off AND its segments
        # already cover the audio — otherwise finalization transcribes the
        # uncovered tail and loads the model.
        needs_whisper = (
            self._session is None
            or self._options.diarize
            or has_uncovered_audio(self._session)
        )
        # Diarization is the only path still pinned to the WhisperX model.
        engine = (
            "whisperx" if self._options.diarize
            else pick_backend(settings_mod.load().backend)
        )
        if needs_whisper and not is_whisper_cached(self._options.model, engine):
            self._log(
                "First run: downloading Whisper model "
                "(~3 GB, 5-15 min on broadband)..."
            )
            self._log("Subsequent runs use the cached model and start instantly.")
        self._log("Finalizing session..." if self._session else "Starting pipeline...")
        self._clock = self.set_interval(1.0, self._tick)
        self.run_worker(self._do_run, thread=True, exclusive=True)

    def _tick(self) -> None:
        self._elapsed += 1
        self.query_one("#file_label", Static).update(
            f"Processing: {self._label_name}   "
            f"{self._elapsed // 60:02d}:{self._elapsed % 60:02d} elapsed"
        )

    def _render_stage_line(self, name: str) -> str:
        s = self._stages[name]
        icons = {
            "waiting":  ("○", "#8C8C8C"),
            "running":  ("▶", "#2DD4BF"),
            "done":     ("✓", "#52C41A"),
            "failed":   ("✗", "#FF4D4F"),
            "skipped":  ("—", "#8C8C8C"),
        }
        status_colors = {
            "waiting":  "#8C8C8C",
            "running":  "#2DD4BF",
            "done":     "#52C41A",
            "failed":   "#FF4D4F",
            "skipped":  "#8C8C8C",
        }
        icon, icon_color = icons.get(s.status, ("○", "#8C8C8C"))
        status_color = status_colors.get(s.status, "#8C8C8C")
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
            if self._session is not None:
                from mynah.core.pipeline import finalize_session

                result = finalize_session(
                    self._session, self._options, on_progress=progress_cb
                )
            else:
                from mynah.core.pipeline import run as run_pipeline

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
        if self._clock is not None:
            self._clock.stop()
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

    def action_back(self) -> None:
        # No mid-run cancel: the pipeline holds no cancellation point, and a
        # button that only logs "cancelling" is worse than no button.
        if self._done:
            self.app.pop_screen()
