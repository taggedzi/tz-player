"""SQLite schema creation and in-place migration steps.

`PRAGMA user_version` is the source of truth for migration state. Migrations are
applied sequentially and are written to be idempotent within their version step.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3

SCHEMA_VERSION = 4
_SCALAR_DEFAULT_PARAMS_JSON = json.dumps(
    {"bucket_ms": 50}, sort_keys=True, separators=(",", ":")
)
_SCALAR_DEFAULT_PARAMS_HASH = hashlib.sha1(
    _SCALAR_DEFAULT_PARAMS_JSON.encode("utf-8")
).hexdigest()

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
    """Create or migrate schema to `SCHEMA_VERSION` in the supplied connection."""
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
        conn.execute("PRAGMA user_version = 3")
        version = 3
    if version == 3:
        _migrate_v3_to_v4(conn)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def _create_schema_v1(conn: sqlite3.Connection) -> None:
    """Create base v1 tables/indexes in a fresh database."""
    for statement in SCHEMA_V1_STATEMENTS:
        conn.execute(statement)


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Migrate playlist items to include a stable item primary key column."""
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
    """Add envelope-analysis cache tables used by audio level services."""
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


def _migrate_v3_to_v4(conn: sqlite3.Connection) -> None:
    """Add generic analysis cache and FFT spectrum frame storage tables."""
    _begin_immediate(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_cache_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_type TEXT NOT NULL,
            path_norm TEXT NOT NULL,
            mtime_ns INTEGER,
            size_bytes INTEGER,
            analysis_version INTEGER NOT NULL,
            params_hash TEXT NOT NULL,
            params_json TEXT NOT NULL,
            duration_ms INTEGER NOT NULL,
            frame_count INTEGER NOT NULL DEFAULT 0,
            byte_size INTEGER NOT NULL DEFAULT 0,
            computed_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
            last_accessed_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
            UNIQUE(path_norm, mtime_ns, size_bytes, analysis_type, analysis_version, params_hash)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_scalar_frames (
            entry_id INTEGER NOT NULL,
            position_ms INTEGER NOT NULL,
            level_left REAL NOT NULL,
            level_right REAL NOT NULL,
            PRIMARY KEY (entry_id, position_ms),
            FOREIGN KEY(entry_id) REFERENCES analysis_cache_entries(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_spectrum_frames (
            entry_id INTEGER NOT NULL,
            frame_idx INTEGER NOT NULL,
            position_ms INTEGER NOT NULL,
            bands BLOB NOT NULL,
            PRIMARY KEY (entry_id, frame_idx),
            FOREIGN KEY(entry_id) REFERENCES analysis_cache_entries(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_analysis_cache_lookup ON analysis_cache_entries(analysis_type, path_norm, analysis_version, params_hash)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_analysis_cache_access ON analysis_cache_entries(last_accessed_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_analysis_cache_computed ON analysis_cache_entries(computed_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_analysis_scalar_pos ON analysis_scalar_frames(entry_id, position_ms)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_analysis_spectrum_pos ON analysis_spectrum_frames(entry_id, position_ms)"
    )
    # Migrate existing scalar envelope cache rows into generic analysis cache tables.
    conn.execute(
        """
        INSERT OR IGNORE INTO analysis_cache_entries (
            analysis_type,
            path_norm,
            mtime_ns,
            size_bytes,
            analysis_version,
            params_hash,
            params_json,
            duration_ms,
            frame_count,
            byte_size,
            computed_at,
            last_accessed_at
        )
        SELECT
            'scalar',
            e.path_norm,
            e.mtime_ns,
            e.size_bytes,
            e.analysis_version,
            ?,
            ?,
            e.duration_ms,
            COUNT(p.position_ms),
            COUNT(p.position_ms) * 24,
            e.computed_at,
            e.computed_at
        FROM audio_envelopes AS e
        LEFT JOIN audio_envelope_points AS p
          ON p.envelope_id = e.id
        GROUP BY
            e.id,
            e.path_norm,
            e.mtime_ns,
            e.size_bytes,
            e.analysis_version,
            e.duration_ms,
            e.computed_at
        """,
        (_SCALAR_DEFAULT_PARAMS_HASH, _SCALAR_DEFAULT_PARAMS_JSON),
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO analysis_scalar_frames (
            entry_id,
            position_ms,
            level_left,
            level_right
        )
        SELECT
            a.id,
            p.position_ms,
            p.level_left,
            p.level_right
        FROM audio_envelopes AS e
        JOIN analysis_cache_entries AS a
          ON a.analysis_type = 'scalar'
         AND a.path_norm = e.path_norm
         AND a.analysis_version = e.analysis_version
         AND a.params_hash = ?
         AND a.params_json = ?
         AND a.mtime_ns IS e.mtime_ns
         AND a.size_bytes IS e.size_bytes
        JOIN audio_envelope_points AS p
          ON p.envelope_id = e.id
        """,
        (_SCALAR_DEFAULT_PARAMS_HASH, _SCALAR_DEFAULT_PARAMS_JSON),
    )


def _begin_immediate(conn: sqlite3.Connection) -> None:
    """Start immediate transaction only when one is not already active."""
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
