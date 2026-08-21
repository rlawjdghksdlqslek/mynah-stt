"""Textual's Header can crash the whole app on shutdown; we patch it.

Upstream's `Header._on_mount` arms a coroutine watcher that does
`query_one(HeaderTitle)`. If the header's children are already unmounted when
it runs, the query raises `NoMatches`, which upstream does not catch. That
killed a real session between `finalize_wav()` and the transcript write.
"""

from __future__ import annotations

import asyncio

from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Static

from mynah.tui.widgets import patch_header_title_race


class _Screen(Screen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static("body")


class _App(App):
    def on_mount(self) -> None:
        self.push_screen(_Screen())


async def _run_the_race() -> None:
    """Unmount the header's children, then trigger the pending title update."""
    app = _App()
    async with app.run_test() as pilot:
        header = app.screen.query_one(Header)
        await header.remove_children()
        app.title = "changed"
        for _ in range(10):
            await pilot.pause()


def test_header_survives_title_update_after_children_are_gone() -> None:
    patch_header_title_race()
    asyncio.run(_run_the_race())  # unpatched this raises NoMatches


def test_patch_is_idempotent() -> None:
    patch_header_title_race()
    first = Header._on_mount
    patch_header_title_race()

    assert Header._on_mount is first
