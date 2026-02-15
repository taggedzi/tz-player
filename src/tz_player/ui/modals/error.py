"""Error modal."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label


class ErrorModal(ModalScreen[None]):
    """Display a short error message."""

    BINDINGS = [
        ("escape", "close", "Close"),
        ("enter", "close", "Close"),
    ]

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message
        self._ok_button: Button | None = None

    def compose(self) -> ComposeResult:
        self._ok_button = Button("OK", id="ok")
        yield Vertical(
            Label(self._message),
            self._ok_button,
            id="modal-body",
        )

    def on_mount(self) -> None:
        if self._ok_button is not None:
            self._ok_button.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        del event
        self.action_close()

    def action_close(self) -> None:
        self.dismiss(None)
