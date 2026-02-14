"""SQLite-backed storage and lookup for precomputed audio envelopes."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from tz_player.services.audio_level_service import EnvelopeLevelProvider
from tz_player.services.playback_backend import LevelSample


class SqliteEnvelopeStore(EnvelopeLevelProvider):
    """Stores and resolves timestamped level envelopes in the app SQLite DB."""

    def __init__(self, db_path: Path, *, analysis_version: int = 1) -> None:
        self._db_path = Path(db_path)
        self._analysis_version = analysis_version

    async def initialize(self) -> None:
        self._initialize_sync()

    async def upsert_envelope(
        self,
        track_path: Path | str,
        points: list[tuple[int, float, float]],
        *,
        duration_ms: int,
    ) -> None:
        self._upsert_envelope_sync(Path(track_path), points, duration_ms)

    async def get_level_at(
        self, track_path: str, position_ms: int
    ) -> LevelSample | None:
        return self._get_level_at_sync(Path(track_path), position_ms)

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

    def _upsert_envelope_sync(
        self,
        track_path: Path,
        points: list[tuple[int, float, float]],
        duration_ms: int,
    ) -> None:
        if not points:
            return
        path_norm = _normalize_path(track_path)
        mtime_ns, size_bytes = _stat_path(track_path)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT INTO audio_envelopes (
                    path_norm, mtime_ns, size_bytes, duration_ms, analysis_version, computed_at
                ) VALUES (?, ?, ?, ?, ?, strftime('%s','now'))
                ON CONFLICT(path_norm) DO UPDATE SET
                    mtime_ns = excluded.mtime_ns,
                    size_bytes = excluded.size_bytes,
                    duration_ms = excluded.duration_ms,
                    analysis_version = excluded.analysis_version,
                    computed_at = excluded.computed_at
                """,
                (
                    path_norm,
                    mtime_ns,
                    size_bytes,
                    max(1, int(duration_ms)),
                    self._analysis_version,
                ),
            )
            row = conn.execute(
                "SELECT id FROM audio_envelopes WHERE path_norm = ? LIMIT 1",
                (path_norm,),
            ).fetchone()
            if row is None:
                return
            envelope_id = int(row["id"])
            conn.execute(
                "DELETE FROM audio_envelope_points WHERE envelope_id = ?",
                (envelope_id,),
            )
            conn.executemany(
                """
                INSERT INTO audio_envelope_points (
                    envelope_id, position_ms, level_left, level_right
                ) VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        envelope_id,
                        max(0, int(position_ms)),
                        _clamp(level_left),
                        _clamp(level_right),
                    )
                    for position_ms, level_left, level_right in points
                ],
            )

    def _get_level_at_sync(
        self, track_path: Path, position_ms: int
    ) -> LevelSample | None:
        path_norm = _normalize_path(track_path)
        mtime_ns, size_bytes = _stat_path(track_path)
        with self._connect() as conn:
            envelope = conn.execute(
                """
                SELECT id
                FROM audio_envelopes
                WHERE path_norm = ?
                  AND analysis_version = ?
                  AND mtime_ns IS ?
                  AND size_bytes IS ?
                LIMIT 1
                """,
                (path_norm, self._analysis_version, mtime_ns, size_bytes),
            ).fetchone()
            if envelope is None:
                return None
            envelope_id = int(envelope["id"])
            pos = max(0, int(position_ms))
            prev_row = conn.execute(
                """
                SELECT position_ms, level_left, level_right
                FROM audio_envelope_points
                WHERE envelope_id = ? AND position_ms <= ?
                ORDER BY position_ms DESC
                LIMIT 1
                """,
                (envelope_id, pos),
            ).fetchone()
            next_row = conn.execute(
                """
                SELECT position_ms, level_left, level_right
                FROM audio_envelope_points
                WHERE envelope_id = ? AND position_ms >= ?
                ORDER BY position_ms ASC
                LIMIT 1
                """,
                (envelope_id, pos),
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


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
