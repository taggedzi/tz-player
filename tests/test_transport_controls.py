"""Tests for transport controls widget."""

from __future__ import annotations

from tz_player.services.player_service import PlayerState
from tz_player.ui.transport_controls import TransportControls


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
