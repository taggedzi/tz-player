"""Tests for metadata service."""

from __future__ import annotations

import asyncio
import wave
from pathlib import Path

from tz_player.services.metadata_service import MetadataService
from tz_player.services.playlist_store import PlaylistStore


def _run(coro):
    return asyncio.run(coro)


def _write_wave(path: Path, duration_sec: float = 0.5, framerate: int = 44100) -> None:
    frames = int(duration_sec * framerate)
    with wave.open(str(path), "wb") as wave_file:
        wave_file.setnchannels(1)
        wave_file.setsampwidth(2)
        wave_file.setframerate(framerate)
        silence = (0).to_bytes(2, byteorder="little", signed=True)
        wave_file.writeframes(silence * frames)


def test_metadata_service_fallback_and_duration(tmp_path) -> None:
    db_path = tmp_path / "library.sqlite"
    store = PlaylistStore(db_path)
    _run(store.initialize())
    playlist_id = _run(store.create_playlist("Default"))

    track_path = tmp_path / "tone.wav"
    _write_wave(track_path)
    _run(store.add_tracks(playlist_id, [track_path]))
    rows = _run(store.fetch_window(playlist_id, 0, 1))
    track_id = rows[0].track_id

    service = MetadataService(store)
    _run(asyncio.wait_for(service.ensure_metadata([track_id]), timeout=5))

    updated = _run(store.fetch_window(playlist_id, 0, 1))[0]
    assert updated.meta_valid is True
    assert updated.title == "tone"
    assert updated.duration_ms is not None
    assert updated.duration_ms > 0


def test_invalidate_if_changed_marks_invalid(tmp_path) -> None:
    db_path = tmp_path / "library.sqlite"
    store = PlaylistStore(db_path)
    _run(store.initialize())
    playlist_id = _run(store.create_playlist("Default"))

    track_path = tmp_path / "tone.wav"
    _write_wave(track_path)
    _run(store.add_tracks(playlist_id, [track_path]))
    rows = _run(store.fetch_window(playlist_id, 0, 1))
    track_id = rows[0].track_id

    service = MetadataService(store)
    _run(asyncio.wait_for(service.ensure_metadata([track_id]), timeout=5))

    track_path.write_bytes(track_path.read_bytes())
    changed = _run(service.invalidate_if_changed(track_id))
    assert changed is True

    updated = _run(store.fetch_window(playlist_id, 0, 1))[0]
    assert updated.meta_valid is False


def test_metadata_service_constructs_without_current_loop(tmp_path) -> None:
    db_path = tmp_path / "library.sqlite"
    store = PlaylistStore(db_path)
    _run(store.initialize())

    asyncio.set_event_loop(None)
    service = MetadataService(store)
    assert service is not None


def test_metadata_service_marks_missing_file_invalid(tmp_path) -> None:
    db_path = tmp_path / "library.sqlite"
    store = PlaylistStore(db_path)
    _run(store.initialize())
    playlist_id = _run(store.create_playlist("Default"))

    track_path = tmp_path / "missing.wav"
    _write_wave(track_path)
    _run(store.add_tracks(playlist_id, [track_path]))
    track_path.unlink()

    rows = _run(store.fetch_window(playlist_id, 0, 1))
    track_id = rows[0].track_id

    service = MetadataService(store)
    _run(asyncio.wait_for(service.ensure_metadata([track_id]), timeout=5))

    updated = _run(store.fetch_window(playlist_id, 0, 1))[0]
    assert updated.meta_valid is False
    assert updated.meta_error == "File missing"
