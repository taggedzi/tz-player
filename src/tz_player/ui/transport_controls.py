"""Transport controls widget for playlist footer."""

from __future__ import annotations

from typing import Literal

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Click, Key
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static

from tz_player.services.player_service import PlayerState


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

    TransportControls .transport-button {
        background: $panel;
        color: $text;
        height: 1;
        padding: 0 1;
        content-align: center middle;
    }

    TransportControls .transport-button:focus {
        background: $boost;
        color: $text;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._track_counter = Static("Track: 0000/0000", id="track-counter")
        self._repeat_button = TransportButton(
            "R:OFF", toggle="repeat", id="repeat-indicator"
        )
        self._shuffle_button = TransportButton(
            "S:OFF", toggle="shuffle", id="shuffle-indicator"
        )
        self._prev_button = TransportButton("<<", action="prev", id="transport-prev")
        self._play_button = TransportButton(
            "PLAY", action="toggle_play", id="transport-play"
        )
        self._stop_button = TransportButton("STOP", action="stop", id="transport-stop")
        self._next_button = TransportButton(">>", action="next", id="transport-next")

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
        self._track_counter.update(counter)
        self._repeat_button.update(f"R:{state.repeat_mode} ")
        shuffle_text = "ON" if state.shuffle else "OFF"
        self._shuffle_button.update(f"S:{shuffle_text} ")
        self._play_button.update("PAUSE" if state.status == "playing" else "PLAY")


class TransportButton(Static):
    def __init__(
        self,
        label: str,
        *,
        action: Literal["prev", "toggle_play", "stop", "next"] | None = None,
        toggle: Literal["repeat", "shuffle"] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(label, classes="transport-button", **kwargs)
        self.action = action
        self.toggle = toggle
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
        if self.action is not None:
            self.post_message(TransportAction(self.action))
        elif self.toggle == "repeat":
            self.post_message(ToggleRepeat())
        elif self.toggle == "shuffle":
            self.post_message(ToggleShuffle())
