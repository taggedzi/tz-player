"""SQLite schema creation and in-place migration steps.

`PRAGMA user_version` is the source of truth for migration state. Migrations are
applied sequentially and are written to be idempotent within their version step.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3

SCHEMA_VERSION = 7
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
        conn.execute("PRAGMA user_version = 4")
        version = 4
    if version == 4:
        _migrate_v4_to_v5(conn)
        conn.execute("PRAGMA user_version = 5")
        version = 5
    if version == 5:
        _migrate_v5_to_v6(conn)
        conn.execute("PRAGMA user_version = 6")
        version = 6
    if version == 6:
        _migrate_v6_to_v7(conn)
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


def _migrate_v4_to_v5(conn: sqlite3.Connection) -> None:
    """Add FTS-backed playlist search index and synchronization triggers."""
    _begin_immediate(conn)
    _create_playlist_search_fts(conn)


def _migrate_v5_to_v6(conn: sqlite3.Connection) -> None:
    """Add beat-analysis cache table for lazy beat/onset reads."""
    _begin_immediate(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_beat_frames (
            entry_id INTEGER NOT NULL,
            frame_idx INTEGER NOT NULL,
            position_ms INTEGER NOT NULL,
            strength_u8 INTEGER NOT NULL,
            is_beat INTEGER NOT NULL DEFAULT 0,
            bpm REAL NOT NULL DEFAULT 0.0,
            PRIMARY KEY (entry_id, frame_idx),
            FOREIGN KEY(entry_id) REFERENCES analysis_cache_entries(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_analysis_beat_pos ON analysis_beat_frames(entry_id, position_ms)"
    )


def _migrate_v6_to_v7(conn: sqlite3.Connection) -> None:
    """Add waveform-proxy cache table for PCM-like min/max envelope frames."""
    _begin_immediate(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_waveform_proxy_frames (
            entry_id INTEGER NOT NULL,
            frame_idx INTEGER NOT NULL,
            position_ms INTEGER NOT NULL,
            min_left_i8 INTEGER NOT NULL,
            max_left_i8 INTEGER NOT NULL,
            min_right_i8 INTEGER NOT NULL,
            max_right_i8 INTEGER NOT NULL,
            PRIMARY KEY (entry_id, frame_idx),
            FOREIGN KEY(entry_id) REFERENCES analysis_cache_entries(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_analysis_waveform_proxy_pos ON analysis_waveform_proxy_frames(entry_id, position_ms)"
    )


def _create_playlist_search_fts(conn: sqlite3.Connection) -> bool:
    """Create and backfill FTS playlist search structures when FTS5 is available."""
    if not _table_exists(conn, "tracks") or not _table_exists(conn, "playlist_items"):
        return False
    has_track_meta = _table_exists(conn, "track_meta")
    try:
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS playlist_search USING fts5(
                item_id UNINDEXED,
                playlist_id UNINDEXED,
                title,
                artist,
                album,
                year,
                path,
                tokenize='unicode61 remove_diacritics 2'
            )
            """
        )
    except sqlite3.OperationalError as exc:
        # Some SQLite builds do not include FTS5; keep LIKE search behavior there.
        if "fts5" in str(exc).lower() or "no such module" in str(exc).lower():
            return False
        raise

    if has_track_meta:
        conn.execute(
            """
            INSERT INTO playlist_search (
                rowid,
                item_id,
                playlist_id,
                title,
                artist,
                album,
                year,
                path
            )
            SELECT
                pi.id,
                pi.id,
                pi.playlist_id,
                COALESCE(tm.title, ''),
                COALESCE(tm.artist, ''),
                COALESCE(tm.album, ''),
                COALESCE(CAST(tm.year AS TEXT), ''),
                COALESCE(t.path, '')
            FROM playlist_items AS pi
            JOIN tracks AS t
              ON t.id = pi.track_id
            LEFT JOIN track_meta AS tm
              ON tm.track_id = t.id
            """
        )
    else:
        conn.execute(
            """
            INSERT INTO playlist_search (
                rowid,
                item_id,
                playlist_id,
                title,
                artist,
                album,
                year,
                path
            )
            SELECT
                pi.id,
                pi.id,
                pi.playlist_id,
                '',
                '',
                '',
                '',
                COALESCE(t.path, '')
            FROM playlist_items AS pi
            JOIN tracks AS t
              ON t.id = pi.track_id
            """
        )
    if has_track_meta:
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_playlist_search_item_insert
            AFTER INSERT ON playlist_items
            BEGIN
                INSERT INTO playlist_search (
                    rowid,
                    item_id,
                    playlist_id,
                    title,
                    artist,
                    album,
                    year,
                    path
                )
                SELECT
                    NEW.id,
                    NEW.id,
                    NEW.playlist_id,
                    COALESCE(tm.title, ''),
                    COALESCE(tm.artist, ''),
                    COALESCE(tm.album, ''),
                    COALESCE(CAST(tm.year AS TEXT), ''),
                    COALESCE(t.path, '')
                FROM tracks AS t
                LEFT JOIN track_meta AS tm
                  ON tm.track_id = t.id
                WHERE t.id = NEW.track_id;
            END
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_playlist_search_item_update
            AFTER UPDATE OF track_id, playlist_id ON playlist_items
            BEGIN
                INSERT OR REPLACE INTO playlist_search (
                    rowid,
                    item_id,
                    playlist_id,
                    title,
                    artist,
                    album,
                    year,
                    path
                )
                SELECT
                    NEW.id,
                    NEW.id,
                    NEW.playlist_id,
                    COALESCE(tm.title, ''),
                    COALESCE(tm.artist, ''),
                    COALESCE(tm.album, ''),
                    COALESCE(CAST(tm.year AS TEXT), ''),
                    COALESCE(t.path, '')
                FROM tracks AS t
                LEFT JOIN track_meta AS tm
                  ON tm.track_id = t.id
                WHERE t.id = NEW.track_id;
            END
            """
        )
    else:
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_playlist_search_item_insert
            AFTER INSERT ON playlist_items
            BEGIN
                INSERT INTO playlist_search (
                    rowid,
                    item_id,
                    playlist_id,
                    title,
                    artist,
                    album,
                    year,
                    path
                )
                SELECT
                    NEW.id,
                    NEW.id,
                    NEW.playlist_id,
                    '',
                    '',
                    '',
                    '',
                    COALESCE(t.path, '')
                FROM tracks AS t
                WHERE t.id = NEW.track_id;
            END
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_playlist_search_item_update
            AFTER UPDATE OF track_id, playlist_id ON playlist_items
            BEGIN
                INSERT OR REPLACE INTO playlist_search (
                    rowid,
                    item_id,
                    playlist_id,
                    title,
                    artist,
                    album,
                    year,
                    path
                )
                SELECT
                    NEW.id,
                    NEW.id,
                    NEW.playlist_id,
                    '',
                    '',
                    '',
                    '',
                    COALESCE(t.path, '')
                FROM tracks AS t
                WHERE t.id = NEW.track_id;
            END
            """
        )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_playlist_search_item_delete
        AFTER DELETE ON playlist_items
        BEGIN
            DELETE FROM playlist_search WHERE rowid = OLD.id;
        END
        """
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_playlist_search_track_path_update
        AFTER UPDATE OF path ON tracks
        BEGIN
            UPDATE playlist_search
            SET path = COALESCE(NEW.path, '')
            WHERE rowid IN (
                SELECT id
                FROM playlist_items
                WHERE track_id = NEW.id
            );
        END
        """
    )
    if has_track_meta:
        conn.execute(
            """
            UPDATE playlist_search
            SET
                title = COALESCE(
                    (SELECT track_meta.title
                     FROM playlist_items
                     JOIN track_meta ON track_meta.track_id = playlist_items.track_id
                     WHERE playlist_items.id = playlist_search.rowid),
                    ''
                ),
                artist = COALESCE(
                    (SELECT track_meta.artist
                     FROM playlist_items
                     JOIN track_meta ON track_meta.track_id = playlist_items.track_id
                     WHERE playlist_items.id = playlist_search.rowid),
                    ''
                ),
                album = COALESCE(
                    (SELECT track_meta.album
                     FROM playlist_items
                     JOIN track_meta ON track_meta.track_id = playlist_items.track_id
                     WHERE playlist_items.id = playlist_search.rowid),
                    ''
                ),
                year = COALESCE(
                    (SELECT CAST(track_meta.year AS TEXT)
                     FROM playlist_items
                     JOIN track_meta ON track_meta.track_id = playlist_items.track_id
                     WHERE playlist_items.id = playlist_search.rowid),
                    ''
                )
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_playlist_search_track_meta_insert
            AFTER INSERT ON track_meta
            BEGIN
                UPDATE playlist_search
                SET
                    title = COALESCE(NEW.title, ''),
                    artist = COALESCE(NEW.artist, ''),
                    album = COALESCE(NEW.album, ''),
                    year = COALESCE(CAST(NEW.year AS TEXT), '')
                WHERE rowid IN (
                    SELECT id
                    FROM playlist_items
                    WHERE track_id = NEW.track_id
                );
            END
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_playlist_search_track_meta_update
            AFTER UPDATE OF title, artist, album, year ON track_meta
            BEGIN
                UPDATE playlist_search
                SET
                    title = COALESCE(NEW.title, ''),
                    artist = COALESCE(NEW.artist, ''),
                    album = COALESCE(NEW.album, ''),
                    year = COALESCE(CAST(NEW.year AS TEXT), '')
                WHERE rowid IN (
                    SELECT id
                    FROM playlist_items
                    WHERE track_id = NEW.track_id
                );
            END
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_playlist_search_track_meta_delete
            AFTER DELETE ON track_meta
            BEGIN
                UPDATE playlist_search
                SET title = '', artist = '', album = '', year = ''
                WHERE rowid IN (
                    SELECT id
                    FROM playlist_items
                    WHERE track_id = OLD.track_id
                );
            END
            """
        )
    return True


def _begin_immediate(conn: sqlite3.Connection) -> None:
    """Start immediate transaction only when one is not already active."""
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()
    return row is not None
