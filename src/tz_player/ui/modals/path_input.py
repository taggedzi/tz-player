"""Path input modal."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label


class PathInputModal(ModalScreen):
    """Modal for entering file or folder paths."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("enter", "submit", "OK"),
    ]

    def __init__(self, title: str, *, placeholder: str = "") -> None:
        super().__init__()
        self._title = title
        self._placeholder = placeholder
        self._input: Input | None = None

    def compose(self) -> ComposeResult:
        self._input = Input(placeholder=self._placeholder, id="path-input")
        yield Vertical(
            Label(self._title),
            self._input,
            Horizontal(
                Button("OK", id="ok"),
                Button("Cancel", id="cancel"),
            ),
            id="modal-body",
        )

    def on_mount(self) -> None:
        if self._input is not None:
            self._input.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ok":
            self.action_submit()
        elif event.button.id == "cancel":
            self.action_cancel()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        del event
        self.action_submit()

    def action_submit(self) -> None:
        value = self._input.value if self._input is not None else ""
        self.dismiss(value.strip() or None)

    def action_cancel(self) -> None:
        self.dismiss(None)
