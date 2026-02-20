"""Retention pruning utilities for shared analysis cache tables."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from tz_player.utils.async_utils import run_blocking


@dataclass(frozen=True)
class AnalysisCachePruneResult:
    """Summary of one prune run."""

    entries_pruned: int
    bytes_before: int
    bytes_after: int

    @property
    def bytes_reclaimed(self) -> int:
        return max(0, self.bytes_before - self.bytes_after)


class SqliteAnalysisCachePruner:
    """Prunes analysis cache entries by age and storage cap."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)

    async def total_cache_bytes(self) -> int:
        return await run_blocking(self._total_cache_bytes_sync)

    async def exceeds_threshold(
        self, *, max_cache_bytes: int, threshold: float
    ) -> bool:
        limit = max(0, int(max_cache_bytes))
        threshold = max(0.0, min(1.0, float(threshold)))
        if limit <= 0:
            return False
        current = await self.total_cache_bytes()
        return current >= int(limit * threshold)

    async def prune(
        self,
        *,
        max_cache_bytes: int,
        max_age_days: int,
        min_recent_tracks_protected: int,
    ) -> AnalysisCachePruneResult:
        return await run_blocking(
            self._prune_sync,
            max_cache_bytes,
            max_age_days,
            min_recent_tracks_protected,
        )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _total_cache_bytes_sync(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(byte_size), 0) AS total_bytes FROM analysis_cache_entries"
            ).fetchone()
            if row is None:
                return 0
            return int(row["total_bytes"])

    def _prune_sync(
        self,
        max_cache_bytes: int,
        max_age_days: int,
        min_recent_tracks_protected: int,
    ) -> AnalysisCachePruneResult:
        max_cache_bytes = max(0, int(max_cache_bytes))
        max_age_days = max(1, int(max_age_days))
        min_recent_tracks_protected = max(0, int(min_recent_tracks_protected))

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            bytes_before = _sum_bytes(conn)
            entries_pruned = 0

            # Age-based prune first while protecting the most recently accessed rows.
            conn.execute(
                """
                DELETE FROM analysis_cache_entries
                WHERE id NOT IN (
                    SELECT id
                    FROM analysis_cache_entries
                    ORDER BY last_accessed_at DESC
                    LIMIT ?
                )
                  AND computed_at < (strftime('%s','now') - (? * 86400))
                """,
                (min_recent_tracks_protected, max_age_days),
            )
            entries_pruned += conn.total_changes

            total_bytes = _sum_bytes(conn)
            if total_bytes > max_cache_bytes:
                rows = conn.execute(
                    """
                    SELECT id, byte_size
                    FROM analysis_cache_entries
                    ORDER BY last_accessed_at ASC
                    """
                ).fetchall()
                protected_ids = {
                    int(row["id"])
                    for row in conn.execute(
                        """
                        SELECT id
                        FROM analysis_cache_entries
                        ORDER BY last_accessed_at DESC
                        LIMIT ?
                        """,
                        (min_recent_tracks_protected,),
                    ).fetchall()
                }
                for row in rows:
                    if total_bytes <= max_cache_bytes:
                        break
                    entry_id = int(row["id"])
                    if entry_id in protected_ids:
                        continue
                    reclaimed = int(row["byte_size"])
                    conn.execute(
                        "DELETE FROM analysis_cache_entries WHERE id = ?",
                        (entry_id,),
                    )
                    entries_pruned += 1
                    total_bytes = max(0, total_bytes - reclaimed)

            bytes_after = _sum_bytes(conn)
            return AnalysisCachePruneResult(
                entries_pruned=entries_pruned,
                bytes_before=bytes_before,
                bytes_after=bytes_after,
            )


def _sum_bytes(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(byte_size), 0) AS total_bytes FROM analysis_cache_entries"
    ).fetchone()
    if row is None:
        return 0
    return int(row["total_bytes"])
