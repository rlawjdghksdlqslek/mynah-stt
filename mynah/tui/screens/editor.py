"""Editor screen — manage glossary terms or replacement rules."""

from __future__ import annotations

from enum import Enum

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

from mynah.config import glossary as glossary_mod
from mynah.config import replacements as replacements_mod
from mynah.config.replacements import Rule


class EditorTarget(str, Enum):
    GLOSSARY = "glossary"
    REPLACEMENTS = "replacements"


class EditorScreen(Screen):
    BINDINGS = [
        ("escape", "close_no_save", "Close (no save)"),
    ]

    DEFAULT_CSS = """
    EditorScreen {
        layout: vertical;
    }
    #content {
        margin: 1 2;
        padding: 1 2;
        height: 1fr;
    }
    .title {
        text-style: bold;
        color: $accent;
    }
    .help {
        color: $text-muted;
        margin-bottom: 1;
    }
    #list {
        height: 1fr;
        border: round $primary;
        margin-bottom: 1;
    }
    #inputs {
        height: auto;
    }
    .input_pair {
        layout: horizontal;
        height: 3;
    }
    .input_pair Label {
        width: 12;
        padding: 1 1 0 1;
    }
    .input_pair Input {
        width: 1fr;
    }
    #buttons {
        height: auto;
        align-horizontal: right;
        margin-top: 1;
    }
    #buttons Button {
        margin-left: 2;
    }
    """

    def __init__(self, target: EditorTarget):
        super().__init__()
        self._target = target
        self._items: list[str] | list[Rule] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="content"):
            if self._target is EditorTarget.GLOSSARY:
                yield Static("Glossary", classes="title")
                yield Static(
                    "Terms below are fed into Whisper as a context hint, "
                    "biasing it to keep proper nouns in their original form "
                    "(e.g. 'Whisper' instead of '위스퍼').",
                    classes="help",
                )
            else:
                yield Static("Replacements", classes="title")
                yield Static(
                    "Literal find/replace rules applied AFTER transcription. "
                    "Useful as a safety net for repeat mistakes "
                    "(e.g. '스랙' → 'Slack').",
                    classes="help",
                )

            yield ListView(id="list")

            with Vertical(id="inputs"):
                if self._target is EditorTarget.GLOSSARY:
                    with Horizontal(classes="input_pair"):
                        yield Label("Term")
                        yield Input(placeholder="e.g. Whisper", id="in_a")
                else:
                    with Horizontal(classes="input_pair"):
                        yield Label("From")
                        yield Input(placeholder="e.g. 스랙", id="in_a")
                    with Horizontal(classes="input_pair"):
                        yield Label("To")
                        yield Input(placeholder="e.g. Slack", id="in_b")

                with Horizontal(id="buttons"):
                    yield Button("Add", id="btn_add")
                    yield Button("Delete selected", id="btn_del")
                    yield Button("Save and close", id="btn_save", variant="success")
                    yield Button("Close (no save)", id="btn_cancel")

        yield Footer()

    def on_mount(self) -> None:
        self._reload()

    def _reload(self) -> None:
        if self._target is EditorTarget.GLOSSARY:
            self._items = glossary_mod.load()
        else:
            self._items = replacements_mod.load()
        listview = self.query_one("#list", ListView)
        listview.clear()
        for it in self._items:
            label = it if isinstance(it, str) else f"{it.src}  →  {it.dst}"
            listview.append(ListItem(Label(label)))

    @on(Button.Pressed, "#btn_add")
    def _on_add(self) -> None:
        a = self.query_one("#in_a", Input).value.strip()
        if not a:
            return
        if self._target is EditorTarget.GLOSSARY:
            assert isinstance(self._items, list)
            if a not in self._items:
                self._items.append(a)
        else:
            b = self.query_one("#in_b", Input).value.strip()
            if not b:
                return
            assert isinstance(self._items, list)
            self._items.append(Rule(src=a, dst=b))
            self.query_one("#in_b", Input).value = ""
        self.query_one("#in_a", Input).value = ""
        self._render_list()

    @on(Button.Pressed, "#btn_del")
    def _on_del(self) -> None:
        listview = self.query_one("#list", ListView)
        index = listview.index
        if index is None:
            return
        if 0 <= index < len(self._items):
            self._items.pop(index)
            self._render_list()

    @on(Button.Pressed, "#btn_save")
    def _on_save(self) -> None:
        if self._target is EditorTarget.GLOSSARY:
            assert all(isinstance(t, str) for t in self._items)
            glossary_mod.save([t for t in self._items if isinstance(t, str)])
        else:
            assert all(isinstance(t, Rule) for t in self._items)
            replacements_mod.save([r for r in self._items if isinstance(r, Rule)])
        self.dismiss(True)

    @on(Button.Pressed, "#btn_cancel")
    def _on_cancel(self) -> None:
        self.dismiss(False)

    def action_close_no_save(self) -> None:
        self.dismiss(False)

    def _render_list(self) -> None:
        listview = self.query_one("#list", ListView)
        listview.clear()
        for it in self._items:
            label = it if isinstance(it, str) else f"{it.src}  →  {it.dst}"
            listview.append(ListItem(Label(label)))
