"""Confirmation modal."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label


class ConfirmModal(ModalScreen[bool]):
    """Simple yes/no confirmation modal."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("enter", "confirm", "Confirm"),
    ]

    def __init__(self, message: str, *, confirm_label: str = "Confirm") -> None:
        super().__init__()
        self._message = message
        self._confirm_label = confirm_label
        self._confirm_button: Button | None = None

    def compose(self) -> ComposeResult:
        self._confirm_button = Button(self._confirm_label, id="confirm")
        yield Vertical(
            Label(self._message),
            Horizontal(
                self._confirm_button,
                Button("Cancel", id="cancel"),
            ),
            id="modal-body",
        )

    def on_mount(self) -> None:
        if self._confirm_button is not None:
            self._confirm_button.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm":
            self.action_confirm()
        else:
            self.action_cancel()

    def action_confirm(self) -> None:
        """Dismiss modal with affirmative result."""
        self.dismiss(True)

    def action_cancel(self) -> None:
        """Dismiss modal with negative result."""
        self.dismiss(False)
