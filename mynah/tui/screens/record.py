"""Recording screen — captures mic input until user stops, then auto
hands the resulting session to the pipeline (via ProgressScreen)."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, ProgressBar, RichLog, Static

from mynah.config import settings as settings_mod
from mynah.core.record import AudioRecorder


class RecordScreen(Screen):
    BINDINGS = [
        ("space", "toggle_pause", "Pause/Resume"),
        ("s", "stop", "Stop & Transcribe"),
        ("escape", "leave", "Exit (keep recording)"),
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
    #live_text {
        height: 10;
        border: round #2DD4BF;
        margin-top: 1;
    }
    .info {
        color: #8C8C8C;
        margin-top: 1;
    }
    """

    SILENT_LEVEL = 0.005
    SILENT_TICKS = 25  # 0.2 s poll -> about 5 s before the warning appears

    def __init__(self, session=None) -> None:
        super().__init__()
        self._session = session
        self._recorder: AudioRecorder | None = None
        self._timer = None
        self._worker = None
        self._worker_stop = None
        self._silent_ticks = 0
        self._stopping = False
        self._wait_dots = 0

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
            yield RichLog(id="live_text", wrap=True, markup=False)
            yield Static(f"Will apply: {opts_summary}", classes="info")
            yield Static("Saving to: session folder", classes="info", id="save_label")
            yield Static(
                "Space · Pause/Resume    S · Stop    Esc · Exit (keeps the recording)",
                classes="info",
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
        from mynah.config import settings as settings_mod
        from mynah.core import session as session_mod

        settings = settings_mod.load()
        session_created_here = self._session is None
        try:
            if self._session is None:
                self._session = session_mod.create(settings.to_options())
            # Resuming appends to an existing audio.pcm, so chunk byte
            # ranges must be offset past what the file already holds —
            # otherwise the worker re-transcribes the old audio.
            # (0 for a fresh session.)
            self._recorder = AudioRecorder(
                output_path=self._session.audio_path,
                base_byte=session_mod.audio_bytes(self._session),
            )
            self._recorder.start()
        except Exception as exc:  # noqa: BLE001 — surface any startup failure
            # Common causes: sounddevice missing, mic permission denied,
            # no input device. All should bounce back to main with a
            # readable message rather than crash the TUI.
            if session_created_here and self._session is not None:
                # Only delete a session we created ourselves here — a
                # session passed into the constructor (resume case) is
                # owned by the caller and must survive.
                import shutil

                shutil.rmtree(self._session.dir, ignore_errors=True)
                self._session = None
            self.app.bell()
            self.notify(str(exc), severity="error")
            self.app.pop_screen()
            return

        self.query_one("#save_label", Static).update(
            f"Saving to: {self._session.dir}"
        )

        if settings.live_transcribe:
            self._start_worker(settings)
            # Chunks are cut at a silence gap no earlier than MIN_CHUNK_SECONDS,
            # so this pane stays empty for the first minute. Say so, or it
            # reads as a hang.
            self.query_one("#live_text", RichLog).write(
                "Listening. The first lines appear after about a minute."
            )
        # The audio callback must not touch Textual; poll instead.
        self._timer = self.set_interval(0.2, self._refresh_timer)

    def on_unmount(self) -> None:
        """Release the mic and release the worker loop on any teardown path.

        Textual waits for threaded workers at shutdown and run_worker's loop
        only exits on the stop event, so quitting mid-recording (Ctrl+Q)
        would otherwise poll forever with the input stream still open.
        """
        try:
            if self._recorder is not None:
                self._recorder.stop()
            if self._worker_stop is not None:
                self._worker_stop.set()
        except Exception:  # noqa: BLE001 — nothing may block teardown
            pass

    def _refresh_timer(self) -> None:
        import math

        if self._stopping:
            # The worker still has the final chunk to transcribe, which takes
            # tens of seconds. Without this the screen sits on one static line
            # and reads as a hang.
            self._wait_dots = (self._wait_dots + 1) % 4
            self.query_one("#status_label", Static).update(
                "⏳ Transcribing the final chunk" + "." * self._wait_dots
            )
            return
        if not self._recorder:
            return
        seconds = int(self._recorder.duration_seconds)
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        timestr = f"{h:02d}:{m:02d}:{s:02d}"
        label = (
            f"⏸ PAUSED   {timestr}" if self._recorder.is_paused
            else f"● REC   {timestr}"
        )

        # Square-root scaling: quiet/distant voices become visible.
        level = self._recorder.level

        # A muted mic or a wrong input device produces a full-length recording
        # of nothing, discovered only after the meeting. Say it during.
        if level < self.SILENT_LEVEL and not self._recorder.is_paused:
            self._silent_ticks += 1
        else:
            self._silent_ticks = 0
        if self._silent_ticks >= self.SILENT_TICKS:
            label += "   ⚠ NO INPUT — check the mic"
        self.query_one("#status_label", Static).update(label)

        visual = math.sqrt(level) if level > 0.0 else 0.0
        self.query_one("#level_meter", ProgressBar).update(progress=int(visual * 100))

    def _start_worker(self, settings) -> None:
        import threading

        from mynah.core.live import run_worker

        self._worker_stop = threading.Event()

        def on_segment(seg: dict) -> None:
            # Worker thread -> UI thread, ~once per chunk. If the screen is
            # already gone, drop the update rather than killing the worker.
            try:
                self.app.call_from_thread(self._append_live_text, seg)
            except Exception:  # noqa: BLE001
                pass

        def work() -> None:
            run_worker(
                self._session,
                self._recorder,
                model_name=settings.model,
                language=settings.language,
                backend=settings.backend,
                on_segment=on_segment,
                stop_event=self._worker_stop,
            )

        self._worker = self.run_worker(work, thread=True, exclusive=False)

    def _append_live_text(self, seg: dict) -> None:
        try:
            log = self.query_one("#live_text", RichLog)
            log.write(seg["text"])
            error = seg.get("error")
            if error:
                log.write(f"[chunk transcription failed: {error}]")
        except Exception:
            pass

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
        # Not `await self.action_stop()`: a Button.Pressed handler runs on the
        # Screen's own message pump, and awaiting the worker there blocks every
        # repaint, freezing the very animation below. Key bindings run on the
        # App pump and were unaffected, which is why this only bit the mouse.
        self.run_worker(self.action_stop(), exclusive=False)

    async def _stop_worker(self) -> None:
        """Signal the transcribe worker and wait for it to drain.

        The worker still has the final chunk to transcribe after the stop
        signal. Returning before it finishes would let finalization read
        transcript.jsonl while the last segment is still being written.
        """
        if self._worker_stop is not None:
            self._worker_stop.set()
        if self._worker is not None:
            try:
                await self._worker.wait()
            except Exception:  # noqa: BLE001 — a dead worker must not block exit
                pass
            self._worker = None

    async def action_stop(self) -> None:
        if not self._recorder:
            self.notify("Recorder not ready", severity="warning")
            return
        try:
            self._recorder.stop()
            self._stopping = True
            await self._stop_worker()
            if self._timer is not None:
                self._timer.stop()

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
            self.app.switch_screen(ProgressScreen(session=self._session, options=opts))
        except Exception as exc:  # noqa: BLE001
            # Without this the screen keeps showing the waiting animation and
            # the clock, meter and no-input warning never come back.
            self._stopping = False
            self.notify(f"Stop failed: {exc}", severity="error")

    async def action_leave(self) -> None:
        """Leave without transcribing. The session stays on disk.

        This used to rmtree the session: one reflexive Esc during a meeting
        destroyed the only copy of it. The main screen's recovery banner
        already offers finish / resume / discard, and its discard needs two
        presses. Nothing here needs to delete anything.
        """
        if self._recorder is not None:
            self._recorder.stop()
            self._recorder = None
        if self._timer is not None:
            self._timer.stop()
        await self._stop_worker()
        self.app.pop_screen()
