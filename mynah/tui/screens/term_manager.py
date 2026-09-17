"""Term Manager screen — tabbed hub for Glossary, Replacements, and Corpus Analysis."""

from __future__ import annotations

from pathlib import Path

from textual import on, work
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
    LoadingIndicator,
    Static,
    TabbedContent,
    TabPane,
)

from mynah.config import corpus_cache
from mynah.config import glossary as glossary_mod
from mynah.config import replacements as replacements_mod
from mynah.config.replacements import Rule
from mynah.core.corpus import Cluster


class TermManagerScreen(Screen):
    BINDINGS = [
        ("escape", "back", "Back"),
        ("q", "back", "Back"),
    ]

    DEFAULT_CSS = """
    TermManagerScreen { layout: vertical; }
    TabbedContent { height: 1fr; }
    .tab_content { margin: 1 2; padding: 1 2; height: 1fr; }
    .section_title { text-style: bold; color: $accent; }
    .section_help { color: $text-muted; margin-bottom: 1; }
    .editor_list { height: 1fr; border: round $primary; margin-bottom: 1; }
    .input_pair { layout: horizontal; height: 3; }
    .input_pair Label { width: 12; padding: 1 1 0 1; }
    .input_pair Input { width: 1fr; }
    .editor_buttons { height: auto; align-horizontal: right; margin-top: 1; }
    .editor_buttons Button { margin-left: 2; }
    #analyze_progress { color: $text-muted; text-align: right; margin-bottom: 1; }
    #analyze_words {
        color: $warning;
        text-style: bold;
        padding: 1 2;
        margin-bottom: 2;
        border: round $surface;
        min-height: 3;
    }
    #analyze_input { margin-bottom: 1; }
    #analyze_card_buttons { height: auto; align-horizontal: right; }
    #analyze_card_buttons Button { margin-left: 2; }
    #analyze_refresh_row { height: auto; margin-top: 2; }
    #analyze_spinner { display: none; height: 1; margin-bottom: 1; }
    """

    def __init__(self, initial_tab: str = "glossary") -> None:
        super().__init__()
        self._initial_tab = initial_tab
        self._glossary_items: list[str] = []
        self._glossary_saved: list[str] = []
        self._replacement_items: list[Rule] = []
        self._replacement_saved: list[Rule] = []
        self._clusters: list[Cluster] = []
        self._pending: list[Cluster] = []
        self._pos: int = 0
        self._analysis_started = False
        self._awaiting_confirm = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with TabbedContent(initial=self._initial_tab):
            with TabPane("Glossary", id="glossary"):
                with Vertical(classes="tab_content"):
                    yield Static("Glossary", classes="section_title")
                    yield Static(
                        "Terms fed into Whisper as context hints "
                        "(e.g. 'Whisper' instead of '위스퍼').",
                        classes="section_help",
                    )
                    yield ListView(id="glossary_list", classes="editor_list")
                    with Horizontal(classes="input_pair"):
                        yield Label("Term")
                        yield Input(placeholder="e.g. Whisper", id="glossary_input")
                    with Horizontal(classes="editor_buttons"):
                        yield Button("Add", id="glossary_add")
                        yield Button("Delete selected", id="glossary_del")
                        yield Button("Save", id="glossary_save", variant="success")

            with TabPane("Replacements", id="replacements"):
                with Vertical(classes="tab_content"):
                    yield Static("Replacements", classes="section_title")
                    yield Static(
                        "Find/replace rules applied AFTER transcription "
                        "(e.g. '스랙' → 'Slack').",
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

            with TabPane("Analyze", id="analyze"):
                with Vertical(classes="tab_content"):
                    yield Static(
                        "Open with T key or click the tab to start analysis.",
                        id="analyze_progress",
                    )
                    yield LoadingIndicator(id="analyze_spinner")
                    yield Static("", id="analyze_words")
                    yield Input(
                        placeholder="Enter correct spelling, then press Enter or Apply",
                        id="analyze_input",
                    )
                    with Horizontal(id="analyze_card_buttons"):
                        yield Button("Skip →", id="analyze_skip")
                        yield Button("Apply →", id="analyze_apply", variant="success")
                    with Horizontal(id="analyze_refresh_row"):
                        yield Button("↺  Re-analyze", id="analyze_refresh", variant="default")

        yield Footer()

    def on_mount(self) -> None:
        self._reload_glossary()
        self._reload_replacements()
        self._set_card_visible(False)
        if self._initial_tab == "analyze":
            self._start_analysis()

    @on(TabbedContent.TabActivated)
    def _on_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        if event.pane.id == "analyze" and not self._analysis_started:
            self._start_analysis()

    def _reload_glossary(self) -> None:
        self._glossary_items = glossary_mod.load()
        self._glossary_saved = list(self._glossary_items)
        self._render_glossary_list()

    def _render_glossary_list(self) -> None:
        lv = self.query_one("#glossary_list", ListView)
        lv.clear()
        for term in self._glossary_items:
            lv.append(ListItem(Label(term)))

    @on(Button.Pressed, "#glossary_add")
    def _glossary_add(self) -> None:
        inp = self.query_one("#glossary_input", Input)
        term = inp.value.strip()
        if not term or term in self._glossary_items:
            return
        self._glossary_items.append(term)
        self.query_one("#glossary_list", ListView).append(ListItem(Label(term)))
        inp.value = ""

    @on(Button.Pressed, "#glossary_del")
    def _glossary_del(self) -> None:
        lv = self.query_one("#glossary_list", ListView)
        idx = lv.index
        if idx is not None and 0 <= idx < len(self._glossary_items):
            self._glossary_items.pop(idx)
            self._render_glossary_list()

    @on(Button.Pressed, "#glossary_save")
    def _glossary_save(self) -> None:
        glossary_mod.save(self._glossary_items)
        self._glossary_saved = list(self._glossary_items)
        self._awaiting_confirm = False
        self.notify("Glossary saved.")

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

    def _set_card_visible(self, visible: bool) -> None:
        self.query_one("#analyze_words", Static).display = visible
        self.query_one("#analyze_input", Input).display = visible
        self.query_one("#analyze_card_buttons", Horizontal).display = visible

    def _start_analysis(self) -> None:
        self._analysis_started = True
        self._set_card_visible(False)
        self.query_one("#analyze_progress", Static).update("Analyzing...")
        self.query_one("#analyze_spinner", LoadingIndicator).display = True
        self._run_analysis()

    @work(exclusive=True, thread=True)
    def _run_analysis(self) -> None:
        from mynah.core.corpus import find_clusters, scan_transcripts

        scan_dir = Path.home() / "Documents" / "mynah-output"
        freq = scan_transcripts([scan_dir])
        clusters = find_clusters(freq)

        existing = corpus_cache.load()
        reviewed_reps = {c.words[0][0] for c in existing if c.reviewed and c.words}
        new_cached = [
            corpus_cache.CachedCluster(
                words=[[w, f] for w, f in c.words],
                reviewed=c.words[0][0] in reviewed_reps,
            )
            for c in clusters
        ]
        corpus_cache.save(new_cached)

        self.app.call_from_thread(self._init_pending, clusters)

    def _init_pending(self, clusters: list[Cluster]) -> None:
        self._clusters = clusters
        reviewed_reps = {
            c.words[0][0] for c in corpus_cache.load() if c.reviewed and c.words
        }
        self._pending = [c for c in self._clusters if c.representative not in reviewed_reps]
        self._pos = 0
        self._show_current()

    def _show_current(self) -> None:
        self.query_one("#analyze_spinner", LoadingIndicator).display = False
        if not self._pending or self._pos >= len(self._pending):
            self._set_card_visible(False)
            self.query_one("#analyze_progress", Static).update(
                "✓ All clusters reviewed"
                if self._clusters
                else "No suspicious terms found."
            )
            return

        cluster = self._pending[self._pos]
        total = len(self._pending)
        self.query_one("#analyze_progress", Static).update(f"{self._pos + 1} / {total}")
        words_str = "  ·  ".join(f"{w}({f})" for w, f in cluster.words)
        self.query_one("#analyze_words", Static).update(f"⚠  {words_str}")
        inp = self.query_one("#analyze_input", Input)
        inp.value = ""
        self._set_card_visible(True)
        inp.focus()

    def _mark_reviewed(self, cluster: Cluster) -> None:
        rep = cluster.representative
        cached = corpus_cache.load()
        for c in cached:
            if c.words and c.words[0][0] == rep:
                c.reviewed = True
                break
        corpus_cache.save(cached)

    @on(Input.Submitted, "#analyze_input")
    def _on_input_submitted(self) -> None:
        self._do_apply()

    @on(Button.Pressed, "#analyze_apply")
    def _on_apply(self) -> None:
        self._do_apply()

    def _do_apply(self) -> None:
        if not self._pending or self._pos >= len(self._pending):
            return
        cluster = self._pending[self._pos]
        canonical = self.query_one("#analyze_input", Input).value.strip()
        if canonical:
            glossary_added = self._add_to_glossary(canonical)
            rules_added = self._add_replacements(cluster, canonical)
            self._notify_apply_result(canonical, glossary_added, rules_added)
        self._mark_reviewed(cluster)
        self._pos += 1
        self._show_current()

    def _add_to_glossary(self, canonical: str) -> bool:
        existing = glossary_mod.load()
        if canonical in existing:
            return False
        glossary_mod.save(existing + [canonical])
        self._reload_glossary()
        return True

    def _add_replacements(self, cluster: Cluster, canonical: str) -> int:
        new_rules = [
            Rule(src=w, dst=canonical) for w, _ in cluster.words if w != canonical
        ]
        existing = replacements_mod.load()
        existing_pairs = {(r.src, r.dst) for r in existing}
        added = [r for r in new_rules if (r.src, r.dst) not in existing_pairs]
        if added:
            replacements_mod.save(existing + added)
            self._reload_replacements()
        return len(added)

    def _notify_apply_result(self, canonical: str, glossary_added: bool, rules_added: int) -> None:
        parts: list[str] = []
        if glossary_added:
            parts.append(f"'{canonical}' added to glossary")
        if rules_added:
            parts.append(f"{rules_added} replacement(s)")
        if parts:
            self.notify(" · ".join(parts))

    @on(Button.Pressed, "#analyze_skip")
    def _on_skip(self) -> None:
        if not self._pending or self._pos >= len(self._pending):
            return
        cluster = self._pending[self._pos]
        self._mark_reviewed(cluster)
        self._pos += 1
        self._show_current()

    @on(Button.Pressed, "#analyze_refresh")
    def _on_refresh(self) -> None:
        self._analysis_started = False
        self._pending = []
        self._pos = 0
        self._start_analysis()

    def action_back(self) -> None:
        glossary_dirty = self._glossary_items != self._glossary_saved
        replacements_dirty = self._replacement_items != self._replacement_saved
        if (glossary_dirty or replacements_dirty) and not self._awaiting_confirm:
            self._awaiting_confirm = True
            self.notify("Unsaved changes. Press Esc again to discard.", severity="warning")
            return
        self.dismiss()
