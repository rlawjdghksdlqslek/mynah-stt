"""Settings screen — all transcription options + HF token in one place.

Replaces the option section that used to live on the main screen.
Reads/writes via mynah.config.settings.
"""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    RadioButton,
    RadioSet,
    Static,
    Switch,
)

from mynah.config import settings as settings_mod


class SettingsScreen(Screen):
    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    SettingsScreen {
        layout: vertical;
    }
    #content {
        margin: 1 2;
        padding: 1 2;
        height: auto;
    }

    /* Toggle option row */
    .option_row {
        height: auto;
        margin-bottom: 1;
        padding: 0 1;
        align: left middle;
    }
    .option_text {
        width: 1fr;
        height: auto;
    }
    .option_label {
        text-style: bold;
    }
    .option_desc {
        color: #595959;
    }
    Switch {
        margin-left: 2;
        align: right middle;
    }

    /* Engine section */
    #model_set, #lang_set {
        layout: horizontal;
        height: auto;
        margin-bottom: 1;
    }

    /* HF token section */
    #token_row {
        height: auto;
        margin-top: 1;
    }

    /* Save / Cancel */
    #buttons {
        margin-top: 2;
        height: auto;
        align-horizontal: right;
    }
    #buttons Button {
        margin-left: 2;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.settings = settings_mod.load()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="content"):

            yield Static("Output", classes="section_title")

            with Horizontal(classes="option_row"):
                with Vertical(classes="option_text"):
                    yield Label("Speaker diarization", classes="option_label")
                    yield Label(
                        "Separate transcript by speaker  (HF token required)",
                        classes="option_desc",
                    )
                yield Switch(value=self.settings.diarize, id="sw_diarize")

            with Horizontal(classes="option_row"):
                with Vertical(classes="option_text"):
                    yield Label("Word-level timestamps", classes="option_label")
                    yield Label(
                        "Prefix each line with [HH:MM:SS]",
                        classes="option_desc",
                    )
                yield Switch(value=self.settings.timestamps, id="sw_timestamps")

            with Horizontal(classes="option_row"):
                with Vertical(classes="option_text"):
                    yield Label("Denoise", classes="option_label")
                    yield Label(
                        "Remove background noise before transcription  (+~10 min)",
                        classes="option_desc",
                    )
                yield Switch(value=self.settings.denoise, id="sw_denoise")

            yield Static("Engine", classes="section_title")
            with RadioSet(id="model_set"):
                yield RadioButton(
                    "large-v3  (accurate)",
                    value=self.settings.model == "large-v3",
                    id="rb_large",
                )
                yield RadioButton(
                    "turbo  (fast)",
                    value=self.settings.model in ("turbo", "large-v3-turbo"),
                    id="rb_turbo",
                )
            with RadioSet(id="lang_set"):
                yield RadioButton(
                    "Korean (ko)", value=self.settings.language == "ko", id="rb_ko"
                )
                yield RadioButton(
                    "English (en)", value=self.settings.language == "en", id="rb_en"
                )
                yield RadioButton(
                    "Auto-detect",
                    value=self.settings.language == "auto",
                    id="rb_auto",
                )

            yield Static("HuggingFace token", classes="section_title")
            yield Static(
                self._token_status_text(),
                id="token_status",
                classes="muted",
            )
            with Horizontal(id="token_row"):
                yield Button(
                    "Set token" if not self.settings.hf_token else "Replace token",
                    id="btn_token",
                )
                if self.settings.hf_token:
                    yield Button("Clear", id="btn_token_clear")
            yield Input(
                placeholder="Paste HuggingFace token (hf_xxx...)",
                id="token_input",
                password=True,
            )

            with Horizontal(id="buttons"):
                yield Button("Cancel", id="btn_cancel")
                yield Button("Save", id="btn_save", variant="success")

        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#token_input", Input).display = False

    def _token_status_text(self) -> str:
        if self.settings.hf_token:
            return "Status: configured"
        return "Status: not set (required for speaker diarization)"

    @on(Button.Pressed, "#btn_token")
    def _on_token_button(self) -> None:
        inp = self.query_one("#token_input", Input)
        inp.display = not inp.display
        if inp.display:
            inp.focus()

    @on(Button.Pressed, "#btn_token_clear")
    def _on_token_clear(self) -> None:
        self.settings.hf_token = ""
        self.query_one("#token_status", Static).update(self._token_status_text())
        self.query_one("#token_input", Input).value = ""

    @on(Button.Pressed, "#btn_cancel")
    def _on_cancel(self) -> None:
        self.dismiss(False)

    def action_cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#btn_save")
    def _on_save(self) -> None:
        self.settings.diarize = self.query_one("#sw_diarize", Switch).value
        self.settings.timestamps = self.query_one("#sw_timestamps", Switch).value
        self.settings.denoise = self.query_one("#sw_denoise", Switch).value

        if self.query_one("#rb_turbo", RadioButton).value:
            self.settings.model = "large-v3-turbo"
        else:
            self.settings.model = "large-v3"

        if self.query_one("#rb_en", RadioButton).value:
            self.settings.language = "en"
        elif self.query_one("#rb_auto", RadioButton).value:
            self.settings.language = "auto"
        else:
            self.settings.language = "ko"

        token_input = self.query_one("#token_input", Input)
        if token_input.display and token_input.value.strip():
            self.settings.hf_token = token_input.value.strip()

        settings_mod.save(self.settings)
        self.dismiss(True)
