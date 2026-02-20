"""SQLite-backed storage and lookup for lazy beat/onset analysis cache."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from tz_player.utils.async_utils import run_blocking


@dataclass(frozen=True)
class BeatParams:
    """Beat-analysis parameters that define cache identity."""

    hop_ms: int = 40
    analyzer: str = "native"


@dataclass(frozen=True)
class BeatFrame:
    """Resolved beat frame sampled for a playback position."""

    position_ms: int
    strength_u8: int
    is_beat: bool
    bpm: float


class SqliteBeatStore:
    """Stores and resolves quantized beat frames in app SQLite DB."""

    ANALYSIS_TYPE = "beat"

    def __init__(self, db_path: Path, *, analysis_version: int = 2) -> None:
        self._db_path = Path(db_path)
        self._analysis_version = analysis_version

    async def initialize(self) -> None:
        await run_blocking(self._initialize_sync)

    async def upsert_beats(
        self,
        track_path: Path | str,
        *,
        duration_ms: int,
        params: BeatParams,
        bpm: float,
        frames: list[tuple[int, int, bool]],
    ) -> None:
        await run_blocking(
            self._upsert_beats_sync,
            Path(track_path),
            duration_ms,
            params,
            bpm,
            frames,
        )

    async def has_beats(self, track_path: Path | str, *, params: BeatParams) -> bool:
        return await run_blocking(self._has_beats_sync, Path(track_path), params)

    async def get_frame_at(
        self,
        track_path: Path | str,
        *,
        position_ms: int,
        params: BeatParams,
    ) -> BeatFrame | None:
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
                "CREATE INDEX IF NOT EXISTS idx_analysis_cache_lookup ON analysis_cache_entries(analysis_type, path_norm, analysis_version, params_hash)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_analysis_beat_pos ON analysis_beat_frames(entry_id, position_ms)"
            )

    def _upsert_beats_sync(
        self,
        track_path: Path,
        duration_ms: int,
        params: BeatParams,
        bpm: float,
        frames: list[tuple[int, int, bool]],
    ) -> None:
        if not frames:
            return
        normalized_frames = [
            (max(0, int(position_ms)), _clamp_u8(strength_u8), int(bool(is_beat)))
            for position_ms, strength_u8, is_beat in frames
        ]
        path_norm = _normalize_path(track_path)
        mtime_ns, size_bytes = _stat_path(track_path)
        params_json = _params_json(params)
        params_hash = _params_hash(params_json)
        total_bytes = len(normalized_frames) * 24
        bpm_value = max(0.0, float(bpm))

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
                "DELETE FROM analysis_beat_frames WHERE entry_id = ?", (entry_id,)
            )
            conn.executemany(
                """
                INSERT INTO analysis_beat_frames (
                    entry_id,
                    frame_idx,
                    position_ms,
                    strength_u8,
                    is_beat,
                    bpm
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (entry_id, idx, position_ms, strength_u8, is_beat, bpm_value)
                    for idx, (position_ms, strength_u8, is_beat) in enumerate(
                        normalized_frames
                    )
                ],
            )

    def _has_beats_sync(self, track_path: Path, params: BeatParams) -> bool:
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
                      FROM analysis_beat_frames AS f
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
        params: BeatParams,
    ) -> BeatFrame | None:
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
            conn.execute(
                "UPDATE analysis_cache_entries SET last_accessed_at = strftime('%s','now') WHERE id = ?",
                (entry_id,),
            )
            prev_row = conn.execute(
                """
                SELECT position_ms, strength_u8, is_beat, bpm
                FROM analysis_beat_frames
                WHERE entry_id = ? AND position_ms <= ?
                ORDER BY position_ms DESC
                LIMIT 1
                """,
                (entry_id, pos),
            ).fetchone()
            next_row = conn.execute(
                """
                SELECT position_ms, strength_u8, is_beat, bpm
                FROM analysis_beat_frames
                WHERE entry_id = ? AND position_ms >= ?
                ORDER BY position_ms ASC
                LIMIT 1
                """,
                (entry_id, pos),
            ).fetchone()
            row_to_use = _nearest_row(prev_row, next_row, target_position_ms=pos)
            if row_to_use is None:
                return None
            if not bool(int(row_to_use["is_beat"])):
                hold_ms = max(120, int(params.hop_ms) * 4)
                beat_row = conn.execute(
                    """
                    SELECT position_ms, strength_u8, is_beat, bpm
                    FROM analysis_beat_frames
                    WHERE entry_id = ?
                      AND is_beat = 1
                      AND position_ms <= ?
                      AND position_ms >= ?
                    ORDER BY position_ms DESC
                    LIMIT 1
                    """,
                    (entry_id, pos, max(0, pos - hold_ms)),
                ).fetchone()
                if beat_row is not None:
                    row_to_use = beat_row
            return BeatFrame(
                position_ms=int(row_to_use["position_ms"]),
                strength_u8=_clamp_u8(int(row_to_use["strength_u8"])),
                is_beat=bool(int(row_to_use["is_beat"])),
                bpm=max(0.0, float(row_to_use["bpm"])),
            )


def _params_json(params: BeatParams) -> str:
    payload = {
        "hop_ms": max(10, int(params.hop_ms)),
        "analyzer": str(params.analyzer or "native").strip().lower(),
    }
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


def _clamp_u8(value: int) -> int:
    return max(0, min(255, int(value)))


def _nearest_row(
    prev_row: sqlite3.Row | None,
    next_row: sqlite3.Row | None,
    *,
    target_position_ms: int,
) -> sqlite3.Row | None:
    if prev_row is None:
        return next_row
    if next_row is None:
        return prev_row
    prev_dist = abs(target_position_ms - int(prev_row["position_ms"]))
    next_dist = abs(int(next_row["position_ms"]) - target_position_ms)
    return prev_row if prev_dist <= next_dist else next_row
