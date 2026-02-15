"""SQLite schema definitions."""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 3

SCHEMA_V1_STATEMENTS = [
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
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise RuntimeError(
            "Unsupported database schema version.\n"
            f"Likely cause: database version {version} is newer than supported version {SCHEMA_VERSION}.\n"
            "Next step: run this tz-player build against a compatible database or upgrade tz-player."
        )
    if version == 0:
        _create_schema_v1(conn)
        conn.execute("PRAGMA user_version = 1")
        version = 1
    if version == 1:
        _migrate_v1_to_v2(conn)
        conn.execute("PRAGMA user_version = 2")
        version = 2
    if version == 2:
        _migrate_v2_to_v3(conn)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def _create_schema_v1(conn: sqlite3.Connection) -> None:
    for statement in SCHEMA_V1_STATEMENTS:
        conn.execute(statement)


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    _begin_immediate(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS playlist_items_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            playlist_id INTEGER NOT NULL,
            track_id INTEGER NOT NULL,
            pos_key INTEGER NOT NULL,
            added_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
            FOREIGN KEY(playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
            FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        INSERT INTO playlist_items_new (playlist_id, track_id, pos_key, added_at)
        SELECT playlist_id, track_id, pos_key, added_at
        FROM playlist_items
        """
    )
    conn.execute("DROP TABLE playlist_items")
    conn.execute("ALTER TABLE playlist_items_new RENAME TO playlist_items")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_playlist_items_playlist_pos ON playlist_items(playlist_id, pos_key)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_playlist_items_playlist_track ON playlist_items(playlist_id, track_id)"
    )


def _migrate_v2_to_v3(conn: sqlite3.Connection) -> None:
    _begin_immediate(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audio_envelopes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path_norm TEXT NOT NULL UNIQUE,
            mtime_ns INTEGER,
            size_bytes INTEGER,
            duration_ms INTEGER NOT NULL,
            analysis_version INTEGER NOT NULL,
            computed_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audio_envelope_points (
            envelope_id INTEGER NOT NULL,
            position_ms INTEGER NOT NULL,
            level_left REAL NOT NULL,
            level_right REAL NOT NULL,
            PRIMARY KEY (envelope_id, position_ms),
            FOREIGN KEY(envelope_id) REFERENCES audio_envelopes(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_audio_envelopes_path_norm ON audio_envelopes(path_norm)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_audio_points_envelope_pos ON audio_envelope_points(envelope_id, position_ms)"
    )


def _begin_immediate(conn: sqlite3.Connection) -> None:
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
