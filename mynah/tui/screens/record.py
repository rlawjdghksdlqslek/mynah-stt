"""Recording screen — captures mic input until user stops, then auto
hands the resulting WAV to the pipeline (via ProgressScreen)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, ProgressBar, Static

from mynah.config import settings as settings_mod
from mynah.core.pipeline import PipelineOptions
from mynah.core.record import AudioRecorder


def _recording_filename(now: dt.datetime | None = None) -> str:
    now = now or dt.datetime.now()
    return f"meeting-{now.strftime('%Y-%m-%d-%H%M%S')}.wav"


def _default_recordings_dir() -> Path:
    return Path.home() / "Documents" / "mynah-recordings"


class RecordScreen(Screen):
    BINDINGS = [
        ("space", "toggle_pause", "Pause/Resume"),
        ("s", "stop", "Stop & Transcribe"),
        ("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    RecordScreen {
        layout: vertical;
    }
    #content {
        margin: 1 2;
        padding: 1 2;
        height: auto;
    }
    #status_label {
        text-style: bold;
        color: #2DD4BF;
        margin-bottom: 1;
    }
    #level_row {
        height: 3;
        margin-bottom: 1;
    }
    #level_row Static {
        width: 8;
    }
    #buttons {
        height: auto;
        margin-top: 1;
    }
    #buttons Button {
        margin-right: 2;
    }
    .info {
        color: #8C8C8C;
        margin-top: 1;
    }
    """

    def __init__(self, output_dir: Path | None = None) -> None:
        super().__init__()
        self._output_dir = output_dir or _default_recordings_dir()
        self._recording_path = self._output_dir / _recording_filename()
        self._recorder: AudioRecorder | None = None
        self._elapsed_s = 0.0
        self._timer = None

    def compose(self) -> ComposeResult:
        settings = settings_mod.load()
        opts_summary = self._summary_for(settings)

        yield Header(show_clock=False)
        with Vertical(id="content"):
            yield Static("● REC   00:00:00", id="status_label")
            with Horizontal(id="level_row"):
                yield Static("Mic:")
                yield ProgressBar(
                    total=100,
                    show_eta=False,
                    show_percentage=False,
                    id="level_meter",
                )
            with Horizontal(id="buttons"):
                yield Button("Pause", id="btn_pause")
                yield Button(
                    "Stop & Transcribe", id="btn_stop", variant="success"
                )
            yield Static(f"Will apply: {opts_summary}", classes="info")
            yield Static(f"Saving to: {self._recording_path.name}", classes="info")
            yield Static(
                "Space · Pause/Resume    S · Stop    Esc · Cancel", classes="info"
            )
        yield Footer()

    def _summary_for(self, settings) -> str:
        parts = [settings.language]
        if settings.diarize:
            parts.append("Diarize")
        if settings.timestamps:
            parts.append("Timestamps")
        if settings.denoise:
            parts.append("Denoise")
        return " · ".join(parts)

    def on_mount(self) -> None:
        try:
            self._recorder = AudioRecorder(
                output_path=self._recording_path,
                on_level=self._on_level,
            )
            self._recorder.start()
        except Exception as exc:  # noqa: BLE001 — surface any startup failure
            # Common causes: sounddevice missing, mic permission denied,
            # no input device. All should bounce back to main with a
            # readable message rather than crash the TUI.
            self.app.bell()
            self.notify(str(exc), severity="error")
            self.app.pop_screen()
            return
        self._timer = self.set_interval(0.5, self._refresh_timer)

    def _on_level(self, level: float) -> None:
        try:
            self.app.call_from_thread(self._update_level, level)
        except Exception:
            pass

    def _update_level(self, level: float) -> None:
        try:
            import math
            bar = self.query_one("#level_meter", ProgressBar)
            # Square-root scaling: small RMS values (quiet/distant voices) become
            # visually meaningful. e.g. RMS 0.02 → bar 14%, not 2%.
            visual = math.sqrt(level) if level > 0.0 else 0.0
            bar.update(progress=int(visual * 100))
        except Exception:
            pass

    def _refresh_timer(self) -> None:
        if not self._recorder:
            return
        seconds = int(self._recorder.duration_seconds)
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        timestr = f"{h:02d}:{m:02d}:{s:02d}"
        if self._recorder.is_paused:
            label = f"⏸ PAUSED   {timestr}"
        else:
            label = f"● REC   {timestr}"
        self.query_one("#status_label", Static).update(label)

    def action_toggle_pause(self) -> None:
        if not self._recorder:
            return
        if self._recorder.is_paused:
            self._recorder.resume()
            self.query_one("#btn_pause", Button).label = "Pause"
        else:
            self._recorder.pause()
            self.query_one("#btn_pause", Button).label = "Resume"

    @on(Button.Pressed, "#btn_pause")
    def _on_pause_button(self) -> None:
        self.action_toggle_pause()

    @on(Button.Pressed, "#btn_stop")
    def _on_stop_button(self) -> None:
        self.action_stop()

    def action_stop(self) -> None:
        if not self._recorder:
            self.notify("Recorder not ready", severity="warning")
            return
        try:
            if self._timer is not None:
                self._timer.stop()
            path = self._recorder.stop()
            self._recorder = None

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

            self.app.switch_screen(ProgressScreen(path, opts))
        except Exception as exc:  # noqa: BLE001
            self.notify(f"Stop failed: {exc}", severity="error")

    def action_cancel(self) -> None:
        if self._recorder is not None:
            self._recorder.stop()
            self._recorder = None
        if self._timer is not None:
            self._timer.stop()
        try:
            self._recording_path.unlink(missing_ok=True)
        except OSError:
            pass
        self.app.pop_screen()
