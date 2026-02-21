"""SQLite-backed storage and lookup for lazy spectrum analysis cache."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from tz_player.utils.async_utils import run_blocking


@dataclass(frozen=True)
class SpectrumParams:
    """Spectrum-analysis parameters that define cache identity."""

    band_count: int = 48
    hop_ms: int = 40


@dataclass(frozen=True)
class SpectrumFrame:
    """Resolved spectrum frame sampled for a playback position."""

    position_ms: int
    bands: bytes


class SqliteSpectrumStore:
    """Stores and resolves quantized spectrum frames in app SQLite DB."""

    ANALYSIS_TYPE = "spectrum"

    def __init__(self, db_path: Path, *, analysis_version: int = 1) -> None:
        self._db_path = Path(db_path)
        self._analysis_version = analysis_version
        self._access_touch_interval_s = 30.0
        self._last_access_touch_s: dict[int, float] = {}

    async def initialize(self) -> None:
        await run_blocking(self._initialize_sync)

    async def upsert_spectrum(
        self,
        track_path: Path | str,
        *,
        duration_ms: int,
        params: SpectrumParams,
        frames: list[tuple[int, bytes]],
    ) -> None:
        await run_blocking(
            self._upsert_spectrum_sync,
            Path(track_path),
            duration_ms,
            params,
            frames,
        )

    async def has_spectrum(
        self, track_path: Path | str, *, params: SpectrumParams
    ) -> bool:
        return await run_blocking(self._has_spectrum_sync, Path(track_path), params)

    async def get_frame_at(
        self,
        track_path: Path | str,
        *,
        position_ms: int,
        params: SpectrumParams,
    ) -> SpectrumFrame | None:
        return await run_blocking(
            self._get_frame_at_sync,
            Path(track_path),
            position_ms,
            params,
        )

    async def prune(
        self,
        *,
        max_cache_bytes: int,
        max_age_days: int,
        min_recent_tracks_protected: int,
    ) -> int:
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

    def _initialize_sync(self) -> None:
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
                "CREATE INDEX IF NOT EXISTS idx_analysis_spectrum_pos ON analysis_spectrum_frames(entry_id, position_ms)"
            )

    def _upsert_spectrum_sync(
        self,
        track_path: Path,
        duration_ms: int,
        params: SpectrumParams,
        frames: list[tuple[int, bytes]],
    ) -> None:
        if not frames:
            return
        normalized_frames = [
            (max(0, int(position_ms)), _normalize_bands(raw, params.band_count))
            for position_ms, raw in frames
        ]
        path_norm = _normalize_path(track_path)
        mtime_ns, size_bytes = _stat_path(track_path)
        params_json = _params_json(params)
        params_hash = _params_hash(params_json)
        total_bytes = sum(len(payload) for _pos, payload in normalized_frames)

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
                    len(normalized_frames),
                    total_bytes,
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
                "DELETE FROM analysis_spectrum_frames WHERE entry_id = ?",
                (entry_id,),
            )
            conn.executemany(
                """
                INSERT INTO analysis_spectrum_frames (
                    entry_id, frame_idx, position_ms, bands
                ) VALUES (?, ?, ?, ?)
                """,
                [
                    (entry_id, idx, position_ms, payload)
                    for idx, (position_ms, payload) in enumerate(normalized_frames)
                ],
            )

    def _has_spectrum_sync(self, track_path: Path, params: SpectrumParams) -> bool:
        path_norm = _normalize_path(track_path)
        mtime_ns, size_bytes = _stat_path(track_path)
        params_hash = _params_hash(_params_json(params))
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
                      FROM analysis_spectrum_frames AS f
                      WHERE f.entry_id = e.id
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

    def _get_frame_at_sync(
        self,
        track_path: Path,
        position_ms: int,
        params: SpectrumParams,
    ) -> SpectrumFrame | None:
        path_norm = _normalize_path(track_path)
        mtime_ns, size_bytes = _stat_path(track_path)
        params_hash = _params_hash(_params_json(params))
        pos = max(0, int(position_ms))
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
            now_s = time.monotonic()
            last_touch_s = self._last_access_touch_s.get(entry_id)
            if (
                last_touch_s is None
                or (now_s - last_touch_s) >= self._access_touch_interval_s
            ):
                conn.execute(
                    "UPDATE analysis_cache_entries SET last_accessed_at = strftime('%s','now') WHERE id = ?",
                    (entry_id,),
                )
                self._last_access_touch_s[entry_id] = now_s
            prev_row = conn.execute(
                """
                SELECT position_ms, bands
                FROM analysis_spectrum_frames
                WHERE entry_id = ? AND position_ms <= ?
                ORDER BY position_ms DESC
                LIMIT 1
                """,
                (entry_id, pos),
            ).fetchone()
            next_row = conn.execute(
                """
                SELECT position_ms, bands
                FROM analysis_spectrum_frames
                WHERE entry_id = ? AND position_ms >= ?
                ORDER BY position_ms ASC
                LIMIT 1
                """,
                (entry_id, pos),
            ).fetchone()
            row_to_use = prev_row or next_row
            if row_to_use is None:
                return None
            return SpectrumFrame(
                position_ms=int(row_to_use["position_ms"]),
                bands=bytes(row_to_use["bands"]),
            )

    def _prune_sync(
        self,
        max_cache_bytes: int,
        max_age_days: int,
        min_recent_tracks_protected: int,
    ) -> int:
        """Prune old/oversized analysis cache entries deterministically."""
        max_cache_bytes = max(0, int(max_cache_bytes))
        max_age_days = max(1, int(max_age_days))
        min_recent_tracks_protected = max(0, int(min_recent_tracks_protected))
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            pruned = 0

            # Age-based prune first, preserving most recent protected entries.
            conn.execute(
                """
                DELETE FROM analysis_cache_entries
                WHERE analysis_type = ?
                  AND id NOT IN (
                      SELECT id
                      FROM analysis_cache_entries
                      WHERE analysis_type = ?
                      ORDER BY last_accessed_at DESC
                      LIMIT ?
                  )
                  AND computed_at < (strftime('%s','now') - (? * 86400))
                """,
                (
                    self.ANALYSIS_TYPE,
                    self.ANALYSIS_TYPE,
                    min_recent_tracks_protected,
                    max_age_days,
                ),
            )
            pruned += conn.total_changes

            total_row = conn.execute(
                "SELECT COALESCE(SUM(byte_size), 0) AS total_bytes FROM analysis_cache_entries WHERE analysis_type = ?",
                (self.ANALYSIS_TYPE,),
            ).fetchone()
            total_bytes = int(total_row["total_bytes"]) if total_row is not None else 0
            if total_bytes <= max_cache_bytes:
                return pruned

            rows = conn.execute(
                """
                SELECT id, byte_size
                FROM analysis_cache_entries
                WHERE analysis_type = ?
                ORDER BY last_accessed_at ASC
                """,
                (self.ANALYSIS_TYPE,),
            ).fetchall()
            protected_ids = {
                int(row["id"])
                for row in conn.execute(
                    """
                    SELECT id
                    FROM analysis_cache_entries
                    WHERE analysis_type = ?
                    ORDER BY last_accessed_at DESC
                    LIMIT ?
                    """,
                    (self.ANALYSIS_TYPE, min_recent_tracks_protected),
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
                pruned += 1
                total_bytes = max(0, total_bytes - reclaimed)
            return pruned


def _params_json(params: SpectrumParams) -> str:
    payload = {
        "band_count": int(params.band_count),
        "hop_ms": int(params.hop_ms),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _params_hash(params_json: str) -> str:
    return hashlib.sha1(params_json.encode("utf-8")).hexdigest()


def _normalize_bands(raw: bytes, band_count: int) -> bytes:
    if len(raw) == band_count:
        return raw
    if len(raw) > band_count:
        return raw[:band_count]
    return raw.ljust(band_count, b"\x00")


def _normalize_path(path: Path) -> str:
    raw = str(path)
    if os.name == "nt":
        return raw.lower()
    return raw


def _stat_path(path: Path) -> tuple[int | None, int | None]:
    try:
        stats = path.stat()
    except OSError:
        return None, None
    return int(stats.st_mtime_ns), int(stats.st_size)
