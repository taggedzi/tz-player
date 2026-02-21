"""SQLite-backed storage and lookup for precomputed audio envelopes."""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
from pathlib import Path

from tz_player.services.audio_level_service import EnvelopeLevelProvider
from tz_player.services.playback_backend import LevelSample
from tz_player.services.sqlite_retry import run_with_sqlite_lock_retry
from tz_player.utils.async_utils import run_blocking


class SqliteEnvelopeStore(EnvelopeLevelProvider):
    """Stores and resolves timestamped level envelopes in the app SQLite DB."""

    ANALYSIS_TYPE = "scalar"

    def __init__(
        self,
        db_path: Path,
        *,
        analysis_version: int = 1,
        bucket_ms: int = 50,
    ) -> None:
        self._db_path = Path(db_path)
        self._analysis_version = analysis_version
        self._bucket_ms = max(10, int(bucket_ms))

    async def initialize(self) -> None:
        await run_blocking(self._initialize_sync)

    async def upsert_envelope(
        self,
        track_path: Path | str,
        points: list[tuple[int, float, float]],
        *,
        duration_ms: int,
    ) -> None:
        await run_blocking(
            self._upsert_envelope_sync, Path(track_path), points, duration_ms
        )

    async def get_level_at(
        self, track_path: str, position_ms: int
    ) -> LevelSample | None:
        return await run_blocking(
            self._get_level_at_sync, Path(track_path), position_ms
        )

    async def has_envelope(self, track_path: Path | str) -> bool:
        return await run_blocking(self._has_envelope_sync, Path(track_path))

    def _connect(self) -> sqlite3.Connection:
        """Create SQLite connection configured for envelope lookups/writes."""
        conn = sqlite3.connect(self._db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _initialize_sync(self) -> None:
        """Create scalar-analysis cache tables/indexes when missing."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
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
                "CREATE INDEX IF NOT EXISTS idx_analysis_cache_lookup ON analysis_cache_entries(analysis_type, path_norm, analysis_version, params_hash)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_analysis_scalar_pos ON analysis_scalar_frames(entry_id, position_ms)"
            )

    def _upsert_envelope_sync(
        self,
        track_path: Path,
        points: list[tuple[int, float, float]],
        duration_ms: int,
    ) -> None:
        """Replace cached envelope and points for track fingerprint."""
        if not points:
            return
        path_norm = _normalize_path(track_path)
        mtime_ns, size_bytes = _stat_path(track_path)
        params_json = _params_json(self._bucket_ms)
        params_hash = _params_hash(params_json)
        normalized_points = [
            (
                max(0, int(position_ms)),
                _clamp(level_left),
                _clamp(level_right),
            )
            for position_ms, level_left, level_right in points
        ]

        def _op() -> None:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    """
                INSERT INTO analysis_cache_entries (
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
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'), strftime('%s','now'))
                ON CONFLICT(path_norm, mtime_ns, size_bytes, analysis_type, analysis_version, params_hash)
                DO UPDATE SET
                    params_json = excluded.params_json,
                    duration_ms = excluded.duration_ms,
                    frame_count = excluded.frame_count,
                    byte_size = excluded.byte_size,
                    computed_at = excluded.computed_at,
                    last_accessed_at = excluded.last_accessed_at
                """,
                    (
                        self.ANALYSIS_TYPE,
                        path_norm,
                        mtime_ns,
                        size_bytes,
                        self._analysis_version,
                        params_hash,
                        params_json,
                        max(1, int(duration_ms)),
                        len(normalized_points),
                        len(normalized_points) * 24,
                    ),
                )
                row = conn.execute(
                    """
                SELECT id
                FROM analysis_cache_entries
                WHERE analysis_type = ?
                  AND path_norm = ?
                  AND analysis_version = ?
                  AND params_hash = ?
                  AND mtime_ns IS ?
                  AND size_bytes IS ?
                LIMIT 1
                """,
                    (
                        self.ANALYSIS_TYPE,
                        path_norm,
                        self._analysis_version,
                        params_hash,
                        mtime_ns,
                        size_bytes,
                    ),
                ).fetchone()
                if row is None:
                    return
                entry_id = int(row["id"])
                conn.execute(
                    "DELETE FROM analysis_scalar_frames WHERE entry_id = ?",
                    (entry_id,),
                )
                conn.executemany(
                    """
                INSERT INTO analysis_scalar_frames (
                    entry_id,
                    position_ms,
                    level_left,
                    level_right
                ) VALUES (?, ?, ?, ?)
                """,
                    [
                        (entry_id, position_ms, level_left, level_right)
                        for position_ms, level_left, level_right in normalized_points
                    ],
                )

        run_with_sqlite_lock_retry(_op, op_name="envelope.upsert")

    def _get_level_at_sync(
        self, track_path: Path, position_ms: int
    ) -> LevelSample | None:
        """Lookup and interpolate envelope level at requested playback position."""
        path_norm = _normalize_path(track_path)
        mtime_ns, size_bytes = _stat_path(track_path)
        params_hash = _params_hash(_params_json(self._bucket_ms))
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id
                FROM analysis_cache_entries
                WHERE analysis_type = ?
                  AND path_norm = ?
                  AND analysis_version = ?
                  AND params_hash = ?
                  AND mtime_ns IS ?
                  AND size_bytes IS ?
                LIMIT 1
                """,
                (
                    self.ANALYSIS_TYPE,
                    path_norm,
                    self._analysis_version,
                    params_hash,
                    mtime_ns,
                    size_bytes,
                ),
            ).fetchone()
            if row is None:
                return None
            entry_id = int(row["id"])
            conn.execute(
                "UPDATE analysis_cache_entries SET last_accessed_at = strftime('%s','now') WHERE id = ?",
                (entry_id,),
            )
            pos = max(0, int(position_ms))
            prev_row = conn.execute(
                """
                SELECT position_ms, level_left, level_right
                FROM analysis_scalar_frames
                WHERE entry_id = ? AND position_ms <= ?
                ORDER BY position_ms DESC
                LIMIT 1
                """,
                (entry_id, pos),
            ).fetchone()
            next_row = conn.execute(
                """
                SELECT position_ms, level_left, level_right
                FROM analysis_scalar_frames
                WHERE entry_id = ? AND position_ms >= ?
                ORDER BY position_ms ASC
                LIMIT 1
                """,
                (entry_id, pos),
            ).fetchone()
            if prev_row is None and next_row is None:
                return None
            if prev_row is None:
                return LevelSample(
                    left=float(next_row["level_left"]),
                    right=float(next_row["level_right"]),
                )
            if next_row is None:
                return LevelSample(
                    left=float(prev_row["level_left"]),
                    right=float(prev_row["level_right"]),
                )
            p0 = int(prev_row["position_ms"])
            p1 = int(next_row["position_ms"])
            l0 = float(prev_row["level_left"])
            r0 = float(prev_row["level_right"])
            l1 = float(next_row["level_left"])
            r1 = float(next_row["level_right"])
            if p1 <= p0:
                return LevelSample(left=l0, right=r0)
            ratio = (pos - p0) / (p1 - p0)
            return LevelSample(
                left=_clamp(l0 + ((l1 - l0) * ratio)),
                right=_clamp(r0 + ((r1 - r0) * ratio)),
            )

    def _has_envelope_sync(self, track_path: Path) -> bool:
        """Return whether valid envelope cache exists for current file fingerprint."""
        path_norm = _normalize_path(track_path)
        mtime_ns, size_bytes = _stat_path(track_path)
        params_hash = _params_hash(_params_json(self._bucket_ms))
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM analysis_cache_entries AS e
                WHERE e.analysis_type = ?
                  AND e.path_norm = ?
                  AND e.analysis_version = ?
                  AND e.params_hash = ?
                  AND e.mtime_ns IS ?
                  AND e.size_bytes IS ?
                  AND EXISTS (
                      SELECT 1
                      FROM analysis_scalar_frames AS p
                      WHERE p.entry_id = e.id
                  )
                LIMIT 1
                """,
                (
                    self.ANALYSIS_TYPE,
                    path_norm,
                    self._analysis_version,
                    params_hash,
                    mtime_ns,
                    size_bytes,
                ),
            ).fetchone()
            return row is not None


def _params_json(bucket_ms: int) -> str:
    payload = {"bucket_ms": int(bucket_ms)}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _params_hash(params_json: str) -> str:
    return hashlib.sha1(params_json.encode("utf-8")).hexdigest()


def _normalize_path(path: Path) -> str:
    """Normalize path key with case folding on Windows for stable lookups."""
    raw = str(path)
    if os.name == "nt":
        return raw.lower()
    return raw


def _stat_path(path: Path) -> tuple[int | None, int | None]:
    """Return file fingerprint tuple used for cache invalidation checks."""
    try:
        stats = path.stat()
    except OSError:
        return None, None
    return int(stats.st_mtime_ns), int(stats.st_size)


def _clamp(value: float) -> float:
    normalized = float(value)
    if not math.isfinite(normalized):
        return 0.0
    return max(0.0, min(1.0, normalized))
