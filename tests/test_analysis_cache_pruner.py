"""Tests for shared analysis cache retention pruning."""

from __future__ import annotations

import asyncio
import sqlite3
import time

from tz_player.db.schema import create_schema
from tz_player.services.analysis_cache_pruner import SqliteAnalysisCachePruner


def _run(coro):
    return asyncio.run(coro)


def _insert_entry(
    conn: sqlite3.Connection,
    *,
    entry_id: int,
    analysis_type: str,
    byte_size: int,
    computed_age_days: int,
    access_age_days: int,
) -> None:
    now = int(time.time())
    conn.execute(
        """
        INSERT INTO analysis_cache_entries (
            id,
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
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entry_id,
            analysis_type,
            f"/tmp/track-{entry_id}.mp3",
            1000 + entry_id,
            2048 + entry_id,
            1,
            "hash",
            "{}",
            1000,
            4,
            byte_size,
            now - (computed_age_days * 86400),
            now - (access_age_days * 86400),
        ),
    )


def test_analysis_cache_pruner_threshold_check(tmp_path) -> None:
    db_path = tmp_path / "library.sqlite"
    with sqlite3.connect(db_path) as conn:
        create_schema(conn)
        _insert_entry(
            conn,
            entry_id=1,
            analysis_type="scalar",
            byte_size=900,
            computed_age_days=1,
            access_age_days=1,
        )

    pruner = SqliteAnalysisCachePruner(db_path)
    assert _run(pruner.exceeds_threshold(max_cache_bytes=1000, threshold=0.90)) is True
    assert _run(pruner.exceeds_threshold(max_cache_bytes=2000, threshold=0.90)) is False


def test_analysis_cache_pruner_prunes_by_age_and_size(tmp_path) -> None:
    db_path = tmp_path / "library.sqlite"
    with sqlite3.connect(db_path) as conn:
        create_schema(conn)
        _insert_entry(
            conn,
            entry_id=1,
            analysis_type="scalar",
            byte_size=300,
            computed_age_days=300,
            access_age_days=300,
        )
        _insert_entry(
            conn,
            entry_id=2,
            analysis_type="spectrum",
            byte_size=400,
            computed_age_days=5,
            access_age_days=5,
        )
        _insert_entry(
            conn,
            entry_id=3,
            analysis_type="spectrum",
            byte_size=500,
            computed_age_days=2,
            access_age_days=2,
        )

    pruner = SqliteAnalysisCachePruner(db_path)
    result = _run(
        pruner.prune(
            max_cache_bytes=600,
            max_age_days=180,
            min_recent_tracks_protected=1,
        )
    )
    assert result.entries_pruned >= 2
    assert result.bytes_before == 1200
    assert result.bytes_after <= 600
    assert result.bytes_reclaimed >= 600

    with sqlite3.connect(db_path) as conn:
        remaining = conn.execute(
            "SELECT COUNT(*) FROM analysis_cache_entries"
        ).fetchone()[0]
    assert remaining == 1
