"""Tests for schema v4->v5 playlist search migration behavior."""

from __future__ import annotations

import sqlite3

from tz_player.db.schema import create_schema


def test_schema_migrates_v4_into_playlist_search_fts(tmp_path) -> None:
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
            CREATE TABLE track_meta (
                track_id INTEGER PRIMARY KEY,
                title TEXT,
                artist TEXT,
                album TEXT,
                year INTEGER,
                duration_ms INTEGER,
                meta_loaded_at INTEGER,
                meta_valid INTEGER NOT NULL DEFAULT 0,
                meta_error TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE playlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE playlist_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                playlist_id INTEGER NOT NULL,
                track_id INTEGER NOT NULL,
                pos_key INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO tracks (path, path_norm) VALUES ('/tmp/moon_song.mp3', '/tmp/moon_song.mp3')"
        )
        track_id = conn.execute("SELECT id FROM tracks").fetchone()[0]
        conn.execute("INSERT INTO playlists (name) VALUES ('Main')")
        playlist_id = conn.execute("SELECT id FROM playlists").fetchone()[0]
        conn.execute(
            """
            INSERT INTO playlist_items (playlist_id, track_id, pos_key)
            VALUES (?, ?, 10000)
            """,
            (playlist_id, track_id),
        )
        conn.execute(
            """
            INSERT INTO track_meta (track_id, title, artist, album, year, meta_valid)
            VALUES (?, 'Moon Song', 'Artist', 'Album', 2024, 1)
            """,
            (track_id,),
        )
        conn.execute("PRAGMA user_version = 4")

        create_schema(conn)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 7

        row = conn.execute(
            """
            SELECT item_id, title, path
            FROM playlist_search
            WHERE playlist_search MATCH 'moon*'
            LIMIT 1
            """
        ).fetchone()
        assert row is not None
        assert int(row[0]) > 0
        assert row[1] == "Moon Song"
        assert row[2] == "/tmp/moon_song.mp3"
