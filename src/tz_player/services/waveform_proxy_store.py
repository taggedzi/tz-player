"""SQLite-backed storage and lookup for waveform-proxy analysis cache."""

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
class WaveformProxyParams:
    """Waveform-proxy parameters that define cache identity."""

    hop_ms: int = 20


@dataclass(frozen=True)
class WaveformProxyFrame:
    """Resolved waveform-proxy frame sampled for playback position."""

    position_ms: int
    min_left_i8: int
    max_left_i8: int
    min_right_i8: int
    max_right_i8: int


class SqliteWaveformProxyStore:
    """Stores and resolves waveform-proxy frames in app SQLite DB."""

    ANALYSIS_TYPE = "waveform_proxy"

    def __init__(self, db_path: Path, *, analysis_version: int = 1) -> None:
        self._db_path = Path(db_path)
        self._analysis_version = analysis_version
        self._access_touch_interval_s = 30.0
        self._last_access_touch_s: dict[int, float] = {}

    async def initialize(self) -> None:
        await run_blocking(self._initialize_sync)

    async def upsert_waveform_proxy(
        self,
        track_path: Path | str,
        *,
        duration_ms: int,
        params: WaveformProxyParams,
        frames: list[tuple[int, int, int, int, int]],
    ) -> None:
        await run_blocking(
            self._upsert_waveform_proxy_sync,
            Path(track_path),
            duration_ms,
            params,
            frames,
        )

    async def has_waveform_proxy(
        self,
        track_path: Path | str,
        *,
        params: WaveformProxyParams,
    ) -> bool:
        return await run_blocking(
            self._has_waveform_proxy_sync,
            Path(track_path),
            params,
        )

    async def get_frame_at(
        self,
        track_path: Path | str,
        *,
        position_ms: int,
        params: WaveformProxyParams,
    ) -> WaveformProxyFrame | None:
        return await run_blocking(
            self._get_frame_at_sync,
            Path(track_path),
            position_ms,
            params,
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
                "CREATE INDEX IF NOT EXISTS idx_analysis_cache_lookup ON analysis_cache_entries(analysis_type, path_norm, analysis_version, params_hash)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_analysis_waveform_proxy_pos ON analysis_waveform_proxy_frames(entry_id, position_ms)"
            )

    def _upsert_waveform_proxy_sync(
        self,
        track_path: Path,
        duration_ms: int,
        params: WaveformProxyParams,
        frames: list[tuple[int, int, int, int, int]],
    ) -> None:
        if not frames:
            return
        normalized_frames = [
            (
                max(0, int(position_ms)),
                _clamp_i8(min_left_i8),
                _clamp_i8(max_left_i8),
                _clamp_i8(min_right_i8),
                _clamp_i8(max_right_i8),
            )
            for (
                position_ms,
                min_left_i8,
                max_left_i8,
                min_right_i8,
                max_right_i8,
            ) in frames
        ]
        path_norm = _normalize_path(track_path)
        mtime_ns, size_bytes = _stat_path(track_path)
        params_json = _params_json(params)
        params_hash = _params_hash(params_json)
        total_bytes = len(normalized_frames) * 8

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
                "DELETE FROM analysis_waveform_proxy_frames WHERE entry_id = ?",
                (entry_id,),
            )
            conn.executemany(
                """
                INSERT INTO analysis_waveform_proxy_frames (
                    entry_id,
                    frame_idx,
                    position_ms,
                    min_left_i8,
                    max_left_i8,
                    min_right_i8,
                    max_right_i8
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        entry_id,
                        idx,
                        position_ms,
                        min_left_i8,
                        max_left_i8,
                        min_right_i8,
                        max_right_i8,
                    )
                    for idx, (
                        position_ms,
                        min_left_i8,
                        max_left_i8,
                        min_right_i8,
                        max_right_i8,
                    ) in enumerate(normalized_frames)
                ],
            )

    def _has_waveform_proxy_sync(
        self,
        track_path: Path,
        params: WaveformProxyParams,
    ) -> bool:
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
                      FROM analysis_waveform_proxy_frames AS f
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
        params: WaveformProxyParams,
    ) -> WaveformProxyFrame | None:
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
                SELECT
                    position_ms,
                    min_left_i8,
                    max_left_i8,
                    min_right_i8,
                    max_right_i8
                FROM analysis_waveform_proxy_frames
                WHERE entry_id = ? AND position_ms <= ?
                ORDER BY position_ms DESC
                LIMIT 1
                """,
                (entry_id, pos),
            ).fetchone()
            next_row = conn.execute(
                """
                SELECT
                    position_ms,
                    min_left_i8,
                    max_left_i8,
                    min_right_i8,
                    max_right_i8
                FROM analysis_waveform_proxy_frames
                WHERE entry_id = ? AND position_ms >= ?
                ORDER BY position_ms ASC
                LIMIT 1
                """,
                (entry_id, pos),
            ).fetchone()
            row_to_use = prev_row or next_row
            if row_to_use is None:
                return None
            return WaveformProxyFrame(
                position_ms=int(row_to_use["position_ms"]),
                min_left_i8=_clamp_i8(int(row_to_use["min_left_i8"])),
                max_left_i8=_clamp_i8(int(row_to_use["max_left_i8"])),
                min_right_i8=_clamp_i8(int(row_to_use["min_right_i8"])),
                max_right_i8=_clamp_i8(int(row_to_use["max_right_i8"])),
            )


def _params_json(params: WaveformProxyParams) -> str:
    payload = {"hop_ms": max(10, int(params.hop_ms))}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _params_hash(params_json: str) -> str:
    return hashlib.sha1(params_json.encode("utf-8")).hexdigest()


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


def _clamp_i8(value: int) -> int:
    return max(-127, min(127, int(value)))
