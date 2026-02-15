"""Transport controls widget for playlist footer."""

from __future__ import annotations

from typing import Literal, cast

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static

from tz_player.services.player_service import PlayerState
from tz_player.ui.text_button import TextButton, TextButtonPressed


class TransportAction(Message):
    bubble = True

    def __init__(self, action: Literal["prev", "toggle_play", "stop", "next"]) -> None:
        super().__init__()
        self.action = action


class ToggleRepeat(Message):
    bubble = True


class ToggleShuffle(Message):
    bubble = True


class TransportControls(Widget):
    DEFAULT_CSS = """
    TransportControls {
        height: 2;
        layout: vertical;
    }

    #transport-line1, #transport-line2 {
        height: 1;
        width: 1fr;
    }

    #track-counter {
        width: 1fr;
    }

    #repeat-indicator, #shuffle-indicator {
        width: auto;
        margin-right: 1;
    }

    #transport-prev, #transport-play, #transport-stop, #transport-next {
        width: 8;
    }

    TransportControls .text-button {
        width: 100%;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._track_counter = Static("Track: 0000/0000", id="track-counter")
        self._repeat_button = TextButton(
            "R:OFF",
            action="repeat",
            id="repeat-indicator",
        )
        self._shuffle_button = TextButton(
            "S:OFF",
            action="shuffle",
            id="shuffle-indicator",
        )
        self._prev_button = TextButton(
            "<<",
            action="prev",
            id="transport-prev",
        )
        self._play_button = TextButton(
            "PLAY",
            action="toggle_play",
            id="transport-play",
        )
        self._stop_button = TextButton(
            "STOP",
            action="stop",
            id="transport-stop",
        )
        self._next_button = TextButton(
            ">>",
            action="next",
            id="transport-next",
        )

    def compose(self) -> ComposeResult:
        yield Vertical(
            Horizontal(
                self._track_counter,
                self._repeat_button,
                self._shuffle_button,
                id="transport-line1",
            ),
            Horizontal(
                self._prev_button,
                self._play_button,
                self._stop_button,
                self._next_button,
                id="transport-line2",
            ),
        )

    def update_from_state(
        self,
        state: PlayerState,
        *,
        total_count: int,
        cursor_index: int | None,
        playing_index: int | None,
    ) -> None:
        current = playing_index if playing_index is not None else cursor_index or 0
        width = max(4, len(str(total_count)))
        if total_count <= 0:
            counter = f"Track: {'0' * width}/{'0' * width}"
        else:
            counter = f"Track: {current:0{width}d}/{total_count:0{width}d}"
        self._track_counter.update(_styled_track_counter_markup(counter))
        self._repeat_button.update(f"R:{state.repeat_mode} ")
        shuffle_text = "ON" if state.shuffle else "OFF"
        self._shuffle_button.update(f"S:{shuffle_text} ")
        self._play_button.update("PAUSE" if state.status == "playing" else "PLAY")

    def on_text_button_pressed(self, event: TextButtonPressed) -> None:
        action = event.action
        if action == "repeat":
            self.post_message(ToggleRepeat())
        elif action == "shuffle":
            self.post_message(ToggleShuffle())
        elif action in {"prev", "toggle_play", "stop", "next"}:
            self.post_message(
                TransportAction(
                    cast(Literal["prev", "toggle_play", "stop", "next"], action)
                )
            )
        else:
            raise ValueError(f"Unsupported transport action: {action}")


def _styled_track_counter_markup(counter: str) -> str:
    label, _, value = counter.partition(" ")
    return f"[bold #F2C94C]{label}[/] {value}"
