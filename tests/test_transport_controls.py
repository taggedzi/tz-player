"""Tests for transport controls widget."""

from __future__ import annotations

from textual.message import Message

from tz_player.services.player_service import PlayerState
from tz_player.ui.text_button import TextButtonPressed
from tz_player.ui.transport_controls import (
    ToggleRepeat,
    ToggleShuffle,
    TransportAction,
    TransportControls,
)


def test_transport_controls_update() -> None:
    controls = TransportControls()
    state = PlayerState(status="playing", repeat_mode="ALL", shuffle=True)
    controls.update_from_state(
        state,
        total_count=12,
        cursor_index=2,
        playing_index=5,
    )
    assert str(controls._play_button.render()) == "PAUSE"
    assert str(controls._repeat_button.render()) == "R:ALL "
    assert str(controls._shuffle_button.render()) == "S:ON "
    assert "Track: 0005/0012" in str(controls._track_counter.render())


def test_transport_controls_button_action_mapping() -> None:
    controls = TransportControls()
    emitted: list[Message] = []

    def capture(message: Message) -> bool:
        emitted.append(message)
        return True

    controls.post_message = capture  # type: ignore[assignment]

    controls.on_text_button_pressed(TextButtonPressed("prev"))
    controls.on_text_button_pressed(TextButtonPressed("toggle_play"))
    controls.on_text_button_pressed(TextButtonPressed("stop"))
    controls.on_text_button_pressed(TextButtonPressed("next"))
    controls.on_text_button_pressed(TextButtonPressed("repeat"))
    controls.on_text_button_pressed(TextButtonPressed("shuffle"))

    assert [type(message).__name__ for message in emitted] == [
        "TransportAction",
        "TransportAction",
        "TransportAction",
        "TransportAction",
        "ToggleRepeat",
        "ToggleShuffle",
    ]
    assert [
        message.action for message in emitted if isinstance(message, TransportAction)
    ] == [
        "prev",
        "toggle_play",
        "stop",
        "next",
    ]
    assert isinstance(emitted[4], ToggleRepeat)
    assert isinstance(emitted[5], ToggleShuffle)
