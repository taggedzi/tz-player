"""Tests for schema v3->v4 analysis cache migration behavior."""

from __future__ import annotations

import sqlite3

from tz_player.db.schema import create_schema


def test_schema_migrates_v3_envelope_rows_into_generic_analysis_cache(tmp_path) -> None:
    db_path = tmp_path / "library.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE audio_envelopes (
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
            CREATE TABLE audio_envelope_points (
                envelope_id INTEGER NOT NULL,
                position_ms INTEGER NOT NULL,
                level_left REAL NOT NULL,
                level_right REAL NOT NULL,
                PRIMARY KEY (envelope_id, position_ms)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO audio_envelopes (
                path_norm,
                mtime_ns,
                size_bytes,
                duration_ms,
                analysis_version,
                computed_at
            ) VALUES ('/tmp/song.mp3', 123, 456, 1000, 1, 1700000000)
            """
        )
        envelope_id = conn.execute(
            "SELECT id FROM audio_envelopes WHERE path_norm = '/tmp/song.mp3'"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO audio_envelope_points (
                envelope_id,
                position_ms,
                level_left,
                level_right
            ) VALUES (?, 0, 0.2, 0.3)
            """,
            (envelope_id,),
        )
        conn.execute("PRAGMA user_version = 3")
        create_schema(conn)

        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 5

        migrated_entry = conn.execute(
            """
            SELECT id, analysis_type, duration_ms, frame_count
            FROM analysis_cache_entries
            WHERE analysis_type = 'scalar'
              AND path_norm = '/tmp/song.mp3'
            """
        ).fetchone()
        assert migrated_entry is not None
        assert migrated_entry[1] == "scalar"
        assert migrated_entry[2] == 1000
        assert migrated_entry[3] == 1

        migrated_point = conn.execute(
            """
            SELECT position_ms, level_left, level_right
            FROM analysis_scalar_frames
            WHERE entry_id = ?
            """,
            (migrated_entry[0],),
        ).fetchone()
        assert migrated_point == (0, 0.2, 0.3)
