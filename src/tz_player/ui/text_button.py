"""Lightweight text button for single-line controls."""

from __future__ import annotations

from textual.events import Click, Key
from textual.message import Message
from textual.widgets import Static


class TextButtonPressed(Message):
    def __init__(self, action: str) -> None:
        super().__init__()
        self.action = action


class TextButton(Static):
    DEFAULT_CSS = """
    .text-button {
        background: $panel;
        color: $text;
        height: 1;
        padding: 0 1;
        content-align: center middle;
    }

    .text-button:focus {
        background: $boost;
        color: $text;
    }
    """

    def __init__(
        self,
        label: str,
        *,
        action: str,
        classes: str | None = "text-button",
        **kwargs,
    ) -> None:
        if not action.strip():
            raise ValueError("action must be non-empty")
        super().__init__(label, classes=classes, **kwargs)
        self.action = action
        self.can_focus = True

    def on_click(self, event: Click) -> None:
        self._emit()
        event.stop()

    def on_key(self, event: Key) -> None:
        if event.key not in {"enter", "space"}:
            return
        self._emit()
        event.stop()

    def _emit(self) -> None:
        self.post_message(TextButtonPressed(self.action))
