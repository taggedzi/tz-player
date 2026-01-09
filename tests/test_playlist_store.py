"""Tests for the playlist store."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from tz_player.services.playlist_store import PlaylistStore


def _run(coro):
    return asyncio.run(coro)


def _touch(path: Path) -> None:
    path.write_bytes(b"")


def test_playlist_store_basic(tmp_path) -> None:
    db_path = tmp_path / "library.sqlite"
    store = PlaylistStore(db_path)

    _run(store.initialize())
    assert db_path.exists()
    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"tracks", "track_meta", "playlists", "playlist_items"}.issubset(tables)

    playlist_id = _run(store.create_playlist("Favorites"))
    track_paths = [tmp_path / f"track_{idx}.mp3" for idx in range(3)]
    for path in track_paths:
        _touch(path)

    added = _run(store.add_tracks(playlist_id, track_paths))
    assert added == 3
    assert _run(store.count(playlist_id)) == 3

    rows = _run(store.fetch_window(playlist_id, 0, 10))
    assert [row.path for row in rows] == track_paths

    removed = _run(store.remove_tracks(playlist_id, {rows[0].track_id}))
    assert removed == 1
    assert _run(store.count(playlist_id)) == 2


def test_move_selection_cursor(tmp_path) -> None:
    db_path = tmp_path / "library.sqlite"
    store = PlaylistStore(db_path)
    _run(store.initialize())
    playlist_id = _run(store.create_playlist("Queue"))

    track_paths = [tmp_path / f"track_{idx}.mp3" for idx in range(3)]
    for path in track_paths:
        _touch(path)
    _run(store.add_tracks(playlist_id, track_paths))

    rows = _run(store.fetch_window(playlist_id, 0, 10))
    cursor_id = rows[1].track_id
    _run(store.move_selection(playlist_id, "up", [], cursor_id))

    updated = _run(store.fetch_window(playlist_id, 0, 10))
    assert updated[0].track_id == cursor_id


def test_invalidate_metadata(tmp_path) -> None:
    db_path = tmp_path / "library.sqlite"
    store = PlaylistStore(db_path)
    _run(store.initialize())
    playlist_id = _run(store.create_playlist("Meta"))

    track_path = tmp_path / "track.mp3"
    _touch(track_path)
    _run(store.add_tracks(playlist_id, [track_path]))
    rows = _run(store.fetch_window(playlist_id, 0, 1))
    track_id = rows[0].track_id

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO track_meta (track_id, title, meta_valid)
            VALUES (?, ?, 1)
            """,
            (track_id, "Song"),
        )

    _run(store.invalidate_metadata({track_id}))

    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            "SELECT meta_valid FROM track_meta WHERE track_id = ?", (track_id,)
        )
        assert cursor.fetchone()[0] == 0
