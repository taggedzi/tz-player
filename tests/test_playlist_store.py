"""Tests for the playlist store."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest

import tz_player.services.playlist_store as playlist_store_module
from tz_player.services.playlist_store import PlaylistStore


def _run(coro):
    """Run async store call from sync pytest test."""
    return asyncio.run(coro)


def _touch(path: Path) -> None:
    """Create empty file used as a fake media track path."""
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
    assert {
        "tracks",
        "track_meta",
        "playlists",
        "playlist_items",
        "audio_envelopes",
        "audio_envelope_points",
    }.issubset(tables)

    playlist_id = _run(store.create_playlist("Favorites"))
    track_paths = [tmp_path / f"track_{idx}.mp3" for idx in range(3)]
    for path in track_paths:
        _touch(path)

    added = _run(store.add_tracks(playlist_id, track_paths))
    assert added == 3
    assert _run(store.count(playlist_id)) == 3

    rows = _run(store.fetch_window(playlist_id, 0, 10))
    assert [row.path for row in rows] == track_paths

    removed = _run(store.remove_items(playlist_id, {rows[0].item_id}))
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
    cursor_id = rows[1].item_id
    _run(store.move_selection(playlist_id, "up", [], cursor_id))

    updated = _run(store.fetch_window(playlist_id, 0, 10))
    assert updated[0].item_id == cursor_id


def test_move_selection_rejects_invalid_direction(tmp_path) -> None:
    db_path = tmp_path / "library.sqlite"
    store = PlaylistStore(db_path)
    _run(store.initialize())
    playlist_id = _run(store.create_playlist("Queue"))

    track_paths = [tmp_path / "track_0.mp3", tmp_path / "track_1.mp3"]
    for path in track_paths:
        _touch(path)
    _run(store.add_tracks(playlist_id, track_paths))

    rows = _run(store.fetch_window(playlist_id, 0, 10))
    with pytest.raises(ValueError, match="direction must be 'up' or 'down'"):
        _run(
            store.move_selection(
                playlist_id,
                "sideways",  # type: ignore[arg-type]
                [rows[0].item_id],
                None,
            )
        )


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


def test_fetch_rows_by_track_ids(tmp_path) -> None:
    db_path = tmp_path / "library.sqlite"
    store = PlaylistStore(db_path)
    _run(store.initialize())
    playlist_id = _run(store.create_playlist("Meta"))

    track_paths = [tmp_path / f"track_{idx}.mp3" for idx in range(3)]
    for path in track_paths:
        _touch(path)
    _run(store.add_tracks(playlist_id, track_paths))
    rows = _run(store.fetch_window(playlist_id, 0, 10))
    track_ids = [row.track_id for row in rows]

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO track_meta (track_id, title, meta_valid)
            VALUES (?, ?, 1)
            """,
            (track_ids[1], "Song"),
        )

    fetched = _run(store.fetch_rows_by_track_ids(playlist_id, track_ids[::-1]))
    assert [row.track_id for row in fetched] == track_ids
    assert fetched[1].title == "Song"
    assert fetched[1].meta_valid is True


def test_duplicate_tracks_allowed(tmp_path) -> None:
    db_path = tmp_path / "library.sqlite"
    store = PlaylistStore(db_path)
    _run(store.initialize())
    playlist_id = _run(store.create_playlist("Dupes"))

    track_path = tmp_path / "track.mp3"
    _touch(track_path)
    _run(store.add_tracks(playlist_id, [track_path, track_path]))
    assert _run(store.count(playlist_id)) == 2
    rows = _run(store.fetch_window(playlist_id, 0, 10))
    assert rows[0].track_id == rows[1].track_id
    assert rows[0].item_id != rows[1].item_id

    _run(store.move_selection(playlist_id, "up", [rows[1].item_id], None))
    moved = _run(store.fetch_window(playlist_id, 0, 10))
    assert moved[0].item_id == rows[1].item_id

    removed = _run(store.remove_items(playlist_id, {rows[0].item_id}))
    assert removed == 1
    assert _run(store.count(playlist_id)) == 1


def test_migration_adds_item_id(tmp_path) -> None:
    db_path = tmp_path / "library.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL UNIQUE,
                path_norm TEXT NOT NULL UNIQUE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE playlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE playlist_items (
                playlist_id INTEGER NOT NULL,
                track_id INTEGER NOT NULL,
                pos_key INTEGER NOT NULL,
                added_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            )
            """
        )
        conn.execute("PRAGMA user_version = 1")

    store = PlaylistStore(db_path)
    _run(store.initialize())
    with sqlite3.connect(db_path) as conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(playlist_items)")]
        assert "id" in columns
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 5


def test_initialize_fails_on_newer_schema_version(tmp_path) -> None:
    db_path = tmp_path / "library.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA user_version = 999")

    store = PlaylistStore(db_path)
    with pytest.raises(RuntimeError) as excinfo:
        _run(store.initialize())

    message = str(excinfo.value)
    assert "Unsupported database schema version." in message
    assert "Likely cause:" in message
    assert "Next step:" in message


def test_search_item_ids_and_fetch_by_item_ids(tmp_path) -> None:
    db_path = tmp_path / "library.sqlite"
    store = PlaylistStore(db_path)
    _run(store.initialize())
    playlist_id = _run(store.create_playlist("Search"))

    track_paths = [
        tmp_path / "moon_song.mp3",
        tmp_path / "sun_song.mp3",
        tmp_path / "moonlight.flac",
    ]
    for path in track_paths:
        _touch(path)

    _run(store.add_tracks(playlist_id, track_paths))
    rows = _run(store.fetch_window(playlist_id, 0, 10))

    match_ids = _run(store.search_item_ids(playlist_id, "moon"))
    assert match_ids == [rows[0].item_id, rows[2].item_id]

    fetched = _run(store.fetch_rows_by_item_ids(playlist_id, match_ids[::-1]))
    assert [row.item_id for row in fetched] == match_ids[::-1]


def test_add_tracks_failure_rolls_back_transaction(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "library.sqlite"
    store = PlaylistStore(db_path)
    _run(store.initialize())
    playlist_id = _run(store.create_playlist("Rollback"))

    paths = [tmp_path / "a.mp3", tmp_path / "b.mp3"]
    for path in paths:
        _touch(path)

    original_stat_path = playlist_store_module._stat_path
    calls = {"count": 0}

    def fail_second_stat(path: Path) -> tuple[int | None, int | None]:
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("simulated stat failure")
        return original_stat_path(path)

    monkeypatch.setattr(playlist_store_module, "_stat_path", fail_second_stat)

    with pytest.raises(OSError):
        _run(store.add_tracks(playlist_id, paths))

    assert _run(store.count(playlist_id)) == 0
    rows = _run(store.fetch_window(playlist_id, 0, 10))
    assert rows == []


def test_get_random_item_id_uses_count_offset_selection(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "library.sqlite"
    store = PlaylistStore(db_path)
    _run(store.initialize())
    playlist_id = _run(store.create_playlist("Random"))

    track_paths = [tmp_path / f"track_{idx}.mp3" for idx in range(4)]
    for path in track_paths:
        _touch(path)
    _run(store.add_tracks(playlist_id, track_paths))
    rows = _run(store.fetch_window(playlist_id, 0, 10))

    monkeypatch.setattr(playlist_store_module.random, "randrange", lambda n: 2)
    selected = _run(store.get_random_item_id(playlist_id))
    assert selected == rows[2].item_id


def test_get_random_item_id_honors_exclusion(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "library.sqlite"
    store = PlaylistStore(db_path)
    _run(store.initialize())
    playlist_id = _run(store.create_playlist("RandomExclude"))

    track_paths = [tmp_path / f"track_{idx}.mp3" for idx in range(3)]
    for path in track_paths:
        _touch(path)
    _run(store.add_tracks(playlist_id, track_paths))
    rows = _run(store.fetch_window(playlist_id, 0, 10))
    excluded = rows[0].item_id

    monkeypatch.setattr(playlist_store_module.random, "randrange", lambda n: 0)
    selected = _run(store.get_random_item_id(playlist_id, exclude_item_id=excluded))
    assert selected in {rows[1].item_id, rows[2].item_id}
    assert selected != excluded


def test_search_item_ids_tracks_metadata_and_path_updates(tmp_path) -> None:
    db_path = tmp_path / "library.sqlite"
    store = PlaylistStore(db_path)
    _run(store.initialize())
    playlist_id = _run(store.create_playlist("SearchUpdates"))

    track_path = tmp_path / "alpha_track.mp3"
    _touch(track_path)
    _run(store.add_tracks(playlist_id, [track_path]))
    row = _run(store.fetch_window(playlist_id, 0, 1))[0]

    assert _run(store.search_item_ids(playlist_id, "alpha")) == [row.item_id]

    _run(
        store.upsert_track_meta(
            row.track_id,
            playlist_store_module.TrackMeta(
                title="Neon Pulse",
                artist="Test Artist",
                album="Perf Set",
                year=2026,
                duration_ms=180000,
                meta_valid=True,
                meta_error=None,
                mtime_ns=None,
                size_bytes=None,
            ),
        )
    )
    assert _run(store.search_item_ids(playlist_id, "neon")) == [row.item_id]

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE tracks SET path = ?, path_norm = ? WHERE id = ?",
            ("retitled/path/new_name.mp3", "retitled/path/new_name.mp3", row.track_id),
        )
    assert _run(store.search_item_ids(playlist_id, "new_name")) == [row.item_id]
