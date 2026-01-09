"""SQLite schema definitions."""

from __future__ import annotations

import sqlite3

SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS tracks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        path TEXT NOT NULL UNIQUE,
        path_norm TEXT NOT NULL UNIQUE,
        mtime_ns INTEGER,
        size_bytes INTEGER,
        created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
        updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS track_meta (
        track_id INTEGER PRIMARY KEY,
        title TEXT,
        artist TEXT,
        album TEXT,
        year INTEGER,
        duration_ms INTEGER,
        meta_loaded_at INTEGER,
        meta_valid INTEGER NOT NULL DEFAULT 0,
        meta_error TEXT,
        FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS playlists (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
        updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS playlist_items (
        playlist_id INTEGER NOT NULL,
        track_id INTEGER NOT NULL,
        pos_key INTEGER NOT NULL,
        added_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
        FOREIGN KEY(playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
        FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_tracks_path_norm ON tracks(path_norm)",
    "CREATE INDEX IF NOT EXISTS idx_track_meta_title ON track_meta(title)",
    "CREATE INDEX IF NOT EXISTS idx_track_meta_artist ON track_meta(artist)",
    "CREATE INDEX IF NOT EXISTS idx_track_meta_album ON track_meta(album)",
    "CREATE INDEX IF NOT EXISTS idx_track_meta_valid ON track_meta(meta_valid)",
    "CREATE INDEX IF NOT EXISTS idx_playlist_items_playlist_pos ON playlist_items(playlist_id, pos_key)",
    "CREATE INDEX IF NOT EXISTS idx_playlist_items_track ON playlist_items(track_id)",
]


def create_schema(conn: sqlite3.Connection) -> None:
    """Create all schema objects in the supplied connection."""
    for statement in SCHEMA_STATEMENTS:
        conn.execute(statement)
