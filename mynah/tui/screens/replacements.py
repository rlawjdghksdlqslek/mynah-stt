"""Replacements screen — find/replace rules applied after transcription."""

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
    ListItem,
    ListView,
    Static,
)

from mynah.config import replacements as replacements_mod
from mynah.config.replacements import Rule


class ReplacementsScreen(Screen):
    BINDINGS = [
        ("escape", "back", "Back"),
        ("q", "back", "Back"),
    ]

    DEFAULT_CSS = """
    ReplacementsScreen { layout: vertical; }
    .body { margin: 1 2; padding: 1 2; height: 1fr; }
    .section_title { text-style: bold; color: $accent; }
    .section_help { color: $text-muted; margin-bottom: 1; }
    .editor_list { height: 1fr; border: round $primary; margin-bottom: 1; }
    .input_pair { layout: horizontal; height: 3; }
    .input_pair Label { width: 12; padding: 1 1 0 1; }
    .input_pair Input { width: 1fr; }
    .editor_buttons { height: auto; align-horizontal: right; margin-top: 1; }
    .editor_buttons Button { margin-left: 2; }
    """

    def __init__(self) -> None:
        super().__init__()
        self._replacement_items: list[Rule] = []
        self._replacement_saved: list[Rule] = []
        self._awaiting_confirm = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(classes="body"):
            yield Static("Replacements", classes="section_title")
            yield Static(
                "Find/replace rules applied AFTER transcription "
                "(e.g. '스랙' → 'Slack'). An ASCII rule matches only when no "
                "other ASCII letter or digit touches it, so 'ok' leaves "
                "'looked' alone but still fixes 'ok입니다'.",
                classes="section_help",
            )
            yield ListView(id="replacements_list", classes="editor_list")
            with Horizontal(classes="input_pair"):
                yield Label("From")
                yield Input(placeholder="e.g. 스랙", id="replacements_from")
            with Horizontal(classes="input_pair"):
                yield Label("To")
                yield Input(placeholder="e.g. Slack", id="replacements_to")
            with Horizontal(classes="editor_buttons"):
                yield Button("Add", id="replacements_add")
                yield Button("Delete selected", id="replacements_del")
                yield Button("Save", id="replacements_save", variant="success")
        yield Footer()

    def on_mount(self) -> None:
        self._reload_replacements()

    def _reload_replacements(self) -> None:
        self._replacement_items = replacements_mod.load()
        self._replacement_saved = list(self._replacement_items)
        self._render_replacements_list()

    def _render_replacements_list(self) -> None:
        lv = self.query_one("#replacements_list", ListView)
        lv.clear()
        for rule in self._replacement_items:
            lv.append(ListItem(Label(f"{rule.src}  →  {rule.dst}")))

    @on(Button.Pressed, "#replacements_add")
    def _replacements_add(self) -> None:
        src = self.query_one("#replacements_from", Input).value.strip()
        dst = self.query_one("#replacements_to", Input).value.strip()
        if not src or not dst:
            return
        self._replacement_items.append(Rule(src=src, dst=dst))
        self.query_one("#replacements_list", ListView).append(
            ListItem(Label(f"{src}  →  {dst}"))
        )
        self.query_one("#replacements_from", Input).value = ""
        self.query_one("#replacements_to", Input).value = ""

    @on(Button.Pressed, "#replacements_del")
    def _replacements_del(self) -> None:
        lv = self.query_one("#replacements_list", ListView)
        idx = lv.index
        if idx is not None and 0 <= idx < len(self._replacement_items):
            self._replacement_items.pop(idx)
            self._render_replacements_list()

    @on(Button.Pressed, "#replacements_save")
    def _replacements_save(self) -> None:
        replacements_mod.save(self._replacement_items)
        self._replacement_saved = list(self._replacement_items)
        self._awaiting_confirm = False
        self.notify("Replacements saved.")

    def action_back(self) -> None:
        if self._replacement_items != self._replacement_saved and not self._awaiting_confirm:
            self._awaiting_confirm = True
            self.notify("Unsaved changes. Press Esc again to discard.", severity="warning")
            return
        self.dismiss()
