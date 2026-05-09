"""Tests for the clipboard helper used by the result screen."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from mynah.tui import clipboard


class TestCopyToClipboard:
    def test_calls_pbcopy_with_text(self) -> None:
        with patch("mynah.tui.clipboard.subprocess.run") as run:
            run.return_value = MagicMock(returncode=0)
            ok = clipboard.copy_to_clipboard("hello world")

        run.assert_called_once()
        args, kwargs = run.call_args
        assert args[0] == ["pbcopy"]
        assert kwargs.get("input") == b"hello world"
        assert ok is True

    def test_handles_unicode(self) -> None:
        with patch("mynah.tui.clipboard.subprocess.run") as run:
            run.return_value = MagicMock(returncode=0)
            ok = clipboard.copy_to_clipboard("안녕하세요")

        kwargs = run.call_args.kwargs
        assert kwargs.get("input") == "안녕하세요".encode()
        assert ok is True

    def test_returns_false_on_pbcopy_failure(self) -> None:
        with patch("mynah.tui.clipboard.subprocess.run") as run:
            run.return_value = MagicMock(returncode=1)
            assert clipboard.copy_to_clipboard("x") is False

    def test_returns_false_when_pbcopy_missing(self) -> None:
        with patch(
            "mynah.tui.clipboard.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            assert clipboard.copy_to_clipboard("x") is False
