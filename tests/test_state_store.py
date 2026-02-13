"""Tests for state storage."""

from __future__ import annotations

from pathlib import Path

import pytest

from tz_player.state_store import AppState, load_state, save_state


def test_state_roundtrip(tmp_path) -> None:
    path = tmp_path / "state.json"
    state = AppState(
        playlist_id=1,
        current_item_id=2,
        volume=0.5,
        speed=1.1,
        repeat_mode="one",
        shuffle=True,
        playback_backend="vlc",
        visualizer_id="bars",
        ansi_enabled=False,
        log_level="DEBUG",
    )

    save_state(path, state)
    loaded = load_state(path)
    assert loaded == state


def test_state_backwards_track_id(tmp_path) -> None:
    path = tmp_path / "state.json"
    path.write_text('{"current_track_id": 5}', encoding="utf-8")
    state = load_state(path)
    assert state.current_item_id == 5


def test_state_corrupt_json_defaults(tmp_path, caplog) -> None:
    path = tmp_path / "state.json"
    path.write_text("{bad json", encoding="utf-8")

    state = load_state(path)
    assert state == AppState()
    assert any("invalid JSON" in record.message for record in caplog.records)


def test_state_save_replace_failure_keeps_previous_file(tmp_path, monkeypatch) -> None:
    path = tmp_path / "state.json"
    original = AppState(playback_backend="fake", visualizer_id="basic")
    save_state(path, original)
    updated = AppState(playback_backend="vlc", visualizer_id="viz.one")

    def fail_replace(self: Path, target: Path) -> None:
        del target
        if self.suffix == ".tmp":
            raise OSError("replace failed")
        return None

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(OSError):
        save_state(path, updated)

    loaded = load_state(path)
    assert loaded == original


def test_state_save_tmp_write_failure_keeps_previous_file(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "state.json"
    original = AppState(playback_backend="fake", visualizer_id="basic")
    save_state(path, original)
    updated = AppState(playback_backend="vlc", visualizer_id="viz.one")

    original_write_text = Path.write_text

    def fail_tmp_write(self: Path, data: str, encoding: str = "utf-8") -> int:
        if self.suffix == ".tmp":
            raise OSError("tmp write failed")
        return original_write_text(self, data, encoding=encoding)

    monkeypatch.setattr(Path, "write_text", fail_tmp_write)

    with pytest.raises(OSError):
        save_state(path, updated)

    loaded = load_state(path)
    assert loaded == original
