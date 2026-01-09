"""Tests for state storage."""

from __future__ import annotations

from tz_player.state_store import AppState, load_state, save_state


def test_state_roundtrip(tmp_path) -> None:
    path = tmp_path / "state.json"
    state = AppState(
        playlist_id=1,
        current_track_id=2,
        volume=0.5,
        speed=1.1,
        repeat_mode="one",
        shuffle=True,
        visualizer_id="bars",
        ansi_enabled=False,
        log_level="DEBUG",
    )

    save_state(path, state)
    loaded = load_state(path)
    assert loaded == state


def test_state_corrupt_json_defaults(tmp_path, caplog) -> None:
    path = tmp_path / "state.json"
    path.write_text("{bad json", encoding="utf-8")

    state = load_state(path)
    assert state == AppState()
    assert any("invalid JSON" in record.message for record in caplog.records)
