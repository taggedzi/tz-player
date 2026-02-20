"""Tests for schema v5->v6 beat cache migration behavior."""

from __future__ import annotations

import sqlite3

from tz_player.db.schema import create_schema


def test_schema_migrates_v5_adds_analysis_beat_frames(tmp_path) -> None:
    db_path = tmp_path / "library.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE analysis_cache_entries (
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
                last_accessed_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            )
            """
        )
        conn.execute("PRAGMA user_version = 5")
        create_schema(conn)

        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 6
        table = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'analysis_beat_frames'
            """
        ).fetchone()
        assert table is not None
