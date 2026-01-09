"""Async SQLite-backed playlist store."""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tz_player.db.schema import create_schema

POS_STEP = 10_000
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlaylistRow:
    track_id: int
    pos_key: int
    path: Path
    title: str | None
    artist: str | None
    album: str | None
    year: int | None
    duration_ms: int | None


class PlaylistStore:
    """SQLite-backed playlist store with async wrappers.

    Each async call uses a fresh SQLite connection to avoid cross-thread access.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    async def create_playlist(self, name: str) -> int:
        return await asyncio.to_thread(self._create_playlist_sync, name)

    async def ensure_playlist(self, name: str) -> int:
        return await asyncio.to_thread(self._ensure_playlist_sync, name)

    async def clear_playlist(self, playlist_id: int) -> None:
        await asyncio.to_thread(self._clear_playlist_sync, playlist_id)

    async def add_tracks(self, playlist_id: int, paths: list[Path]) -> int:
        return await asyncio.to_thread(self._add_tracks_sync, playlist_id, paths)

    async def remove_tracks(self, playlist_id: int, track_ids: set[int]) -> int:
        return await asyncio.to_thread(self._remove_tracks_sync, playlist_id, track_ids)

    async def count(self, playlist_id: int) -> int:
        return await asyncio.to_thread(self._count_sync, playlist_id)

    async def fetch_window(
        self, playlist_id: int, offset: int, limit: int
    ) -> list[PlaylistRow]:
        return await asyncio.to_thread(
            self._fetch_window_sync, playlist_id, offset, limit
        )

    async def fetch_track(self, playlist_id: int, track_id: int) -> PlaylistRow | None:
        return await asyncio.to_thread(self._fetch_track_sync, playlist_id, track_id)

    async def get_next_track_id(
        self, playlist_id: int, track_id: int, *, wrap: bool
    ) -> int | None:
        return await asyncio.to_thread(
            self._get_next_track_id_sync, playlist_id, track_id, wrap
        )

    async def get_prev_track_id(
        self, playlist_id: int, track_id: int, *, wrap: bool
    ) -> int | None:
        return await asyncio.to_thread(
            self._get_prev_track_id_sync, playlist_id, track_id, wrap
        )

    async def move_selection(
        self,
        playlist_id: int,
        direction: Literal["up", "down"],
        selection: list[int],
        cursor: int | None,
    ) -> None:
        await asyncio.to_thread(
            self._move_selection_sync, playlist_id, direction, selection, cursor
        )

    async def invalidate_metadata(self, track_ids: set[int] | None = None) -> None:
        await asyncio.to_thread(self._invalidate_metadata_sync, track_ids)

    async def renumber_playlist(self, playlist_id: int) -> None:
        await asyncio.to_thread(self._renumber_playlist_sync, playlist_id)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _initialize_sync(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            create_schema(conn)
            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()[0]
            logger.info(
                "SQLite pragmas: journal_mode=%s foreign_keys=%s",
                journal_mode,
                foreign_keys,
            )

    def _create_playlist_sync(self, name: str) -> int:
        with self._connect() as conn:
            cursor = conn.execute("INSERT INTO playlists (name) VALUES (?)", (name,))
            if cursor.lastrowid is None:
                raise RuntimeError("Failed to create playlist row.")
            return int(cursor.lastrowid)

    def _ensure_playlist_sync(self, name: str) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT id FROM playlists WHERE name = ? LIMIT 1", (name,)
            )
            row = cursor.fetchone()
            if row is not None:
                return int(row["id"])
            cursor = conn.execute("INSERT INTO playlists (name) VALUES (?)", (name,))
            if cursor.lastrowid is None:
                raise RuntimeError("Failed to create playlist row.")
            return int(cursor.lastrowid)

    def _clear_playlist_sync(self, playlist_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM playlist_items WHERE playlist_id = ?", (playlist_id,)
            )

    def _add_tracks_sync(self, playlist_id: int, paths: list[Path]) -> int:
        if not paths:
            return 0

        added = 0
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                "SELECT COALESCE(MAX(pos_key), 0) FROM playlist_items WHERE playlist_id = ?",
                (playlist_id,),
            )
            next_pos = int(cursor.fetchone()[0]) + POS_STEP
            for path in paths:
                path_value = str(path)
                path_norm = _normalize_path(path)
                track_id = _get_track_id(conn, path_norm)
                if track_id is None:
                    mtime_ns, size_bytes = _stat_path(path)
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO tracks (path, path_norm, mtime_ns, size_bytes)
                        VALUES (?, ?, ?, ?)
                        """,
                        (path_value, path_norm, mtime_ns, size_bytes),
                    )
                    track_id = _get_track_id(conn, path_norm)
                if track_id is None:
                    continue
                conn.execute(
                    """
                    INSERT INTO playlist_items (playlist_id, track_id, pos_key)
                    VALUES (?, ?, ?)
                    """,
                    (playlist_id, track_id, next_pos),
                )
                next_pos += POS_STEP
                added += 1
        return added

    def _remove_tracks_sync(self, playlist_id: int, track_ids: set[int]) -> int:
        if not track_ids:
            return 0
        placeholders = ", ".join("?" for _ in track_ids)
        params: list[int] = [playlist_id, *track_ids]
        with self._connect() as conn:
            cursor = conn.execute(
                f"""
                DELETE FROM playlist_items
                WHERE playlist_id = ? AND track_id IN ({placeholders})
                """,
                params,
            )
            return int(cursor.rowcount or 0)

    def _count_sync(self, playlist_id: int) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM playlist_items WHERE playlist_id = ?",
                (playlist_id,),
            )
            return int(cursor.fetchone()[0])

    def _fetch_window_sync(
        self, playlist_id: int, offset: int, limit: int
    ) -> list[PlaylistRow]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    playlist_items.track_id,
                    playlist_items.pos_key,
                    tracks.path,
                    track_meta.title,
                    track_meta.artist,
                    track_meta.album,
                    track_meta.year,
                    track_meta.duration_ms
                FROM playlist_items
                JOIN tracks ON tracks.id = playlist_items.track_id
                LEFT JOIN track_meta ON track_meta.track_id = tracks.id
                WHERE playlist_items.playlist_id = ?
                ORDER BY playlist_items.pos_key
                LIMIT ? OFFSET ?
                """,
                (playlist_id, limit, offset),
            ).fetchall()
        return [
            PlaylistRow(
                track_id=int(row["track_id"]),
                pos_key=int(row["pos_key"]),
                path=Path(row["path"]),
                title=row["title"],
                artist=row["artist"],
                album=row["album"],
                year=row["year"],
                duration_ms=row["duration_ms"],
            )
            for row in rows
        ]

    def _fetch_track_sync(self, playlist_id: int, track_id: int) -> PlaylistRow | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    playlist_items.track_id,
                    playlist_items.pos_key,
                    tracks.path,
                    track_meta.title,
                    track_meta.artist,
                    track_meta.album,
                    track_meta.year,
                    track_meta.duration_ms
                FROM playlist_items
                JOIN tracks ON tracks.id = playlist_items.track_id
                LEFT JOIN track_meta ON track_meta.track_id = tracks.id
                WHERE playlist_items.playlist_id = ? AND playlist_items.track_id = ?
                LIMIT 1
                """,
                (playlist_id, track_id),
            ).fetchone()
        if row is None:
            return None
        return PlaylistRow(
            track_id=int(row["track_id"]),
            pos_key=int(row["pos_key"]),
            path=Path(row["path"]),
            title=row["title"],
            artist=row["artist"],
            album=row["album"],
            year=row["year"],
            duration_ms=row["duration_ms"],
        )

    def _get_next_track_id_sync(
        self, playlist_id: int, track_id: int, wrap: bool
    ) -> int | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT pos_key
                FROM playlist_items
                WHERE playlist_id = ? AND track_id = ?
                """,
                (playlist_id, track_id),
            ).fetchone()
            if row is None:
                return None
            pos_key = int(row["pos_key"])
            next_row = conn.execute(
                """
                SELECT track_id
                FROM playlist_items
                WHERE playlist_id = ? AND pos_key > ?
                ORDER BY pos_key ASC
                LIMIT 1
                """,
                (playlist_id, pos_key),
            ).fetchone()
            if next_row is not None:
                return int(next_row["track_id"])
            if not wrap:
                return None
            wrap_row = conn.execute(
                """
                SELECT track_id
                FROM playlist_items
                WHERE playlist_id = ?
                ORDER BY pos_key ASC
                LIMIT 1
                """,
                (playlist_id,),
            ).fetchone()
            if wrap_row is None:
                return None
            return int(wrap_row["track_id"])

    def _get_prev_track_id_sync(
        self, playlist_id: int, track_id: int, wrap: bool
    ) -> int | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT pos_key
                FROM playlist_items
                WHERE playlist_id = ? AND track_id = ?
                """,
                (playlist_id, track_id),
            ).fetchone()
            if row is None:
                return None
            pos_key = int(row["pos_key"])
            prev_row = conn.execute(
                """
                SELECT track_id
                FROM playlist_items
                WHERE playlist_id = ? AND pos_key < ?
                ORDER BY pos_key DESC
                LIMIT 1
                """,
                (playlist_id, pos_key),
            ).fetchone()
            if prev_row is not None:
                return int(prev_row["track_id"])
            if not wrap:
                return None
            wrap_row = conn.execute(
                """
                SELECT track_id
                FROM playlist_items
                WHERE playlist_id = ?
                ORDER BY pos_key DESC
                LIMIT 1
                """,
                (playlist_id,),
            ).fetchone()
            if wrap_row is None:
                return None
            return int(wrap_row["track_id"])

    def _move_selection_sync(
        self,
        playlist_id: int,
        direction: Literal["up", "down"],
        selection: list[int],
        cursor: int | None,
    ) -> None:
        if not selection and cursor is None:
            return
        selection_ids = set(selection or ([cursor] if cursor is not None else []))
        if not selection_ids:
            return

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """
                SELECT track_id, pos_key
                FROM playlist_items
                WHERE playlist_id = ?
                ORDER BY pos_key
                """,
                (playlist_id,),
            ).fetchall()
            if not rows:
                return
            track_ids = [int(row["track_id"]) for row in rows]
            pos_keys = [int(row["pos_key"]) for row in rows]

            if direction == "up":
                for index in range(1, len(track_ids)):
                    if (
                        track_ids[index] in selection_ids
                        and track_ids[index - 1] not in selection_ids
                    ):
                        track_ids[index - 1], track_ids[index] = (
                            track_ids[index],
                            track_ids[index - 1],
                        )
            else:
                for index in range(len(track_ids) - 2, -1, -1):
                    if (
                        track_ids[index] in selection_ids
                        and track_ids[index + 1] not in selection_ids
                    ):
                        track_ids[index + 1], track_ids[index] = (
                            track_ids[index],
                            track_ids[index + 1],
                        )

            updates = [
                (pos_keys[i], playlist_id, track_ids[i]) for i in range(len(track_ids))
            ]
            conn.executemany(
                """
                UPDATE playlist_items
                SET pos_key = ?
                WHERE playlist_id = ? AND track_id = ?
                """,
                updates,
            )

    def _invalidate_metadata_sync(self, track_ids: set[int] | None) -> None:
        with self._connect() as conn:
            if not track_ids:
                conn.execute("UPDATE track_meta SET meta_valid = 0")
                return
            placeholders = ", ".join("?" for _ in track_ids)
            conn.execute(
                f"UPDATE track_meta SET meta_valid = 0 WHERE track_id IN ({placeholders})",
                list(track_ids),
            )

    def _renumber_playlist_sync(self, playlist_id: int) -> None:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """
                SELECT track_id
                FROM playlist_items
                WHERE playlist_id = ?
                ORDER BY pos_key
                """,
                (playlist_id,),
            ).fetchall()
            updates = []
            next_pos = POS_STEP
            for row in rows:
                updates.append((next_pos, playlist_id, int(row["track_id"])))
                next_pos += POS_STEP
            conn.executemany(
                """
                UPDATE playlist_items
                SET pos_key = ?
                WHERE playlist_id = ? AND track_id = ?
                """,
                updates,
            )


def _normalize_path(path: Path) -> str:
    return os.path.normcase(str(path.expanduser().resolve(strict=False)))


def _stat_path(path: Path) -> tuple[int | None, int | None]:
    try:
        stat = path.stat()
    except OSError:
        return None, None
    return stat.st_mtime_ns, stat.st_size


def _get_track_id(conn: sqlite3.Connection, path_norm: str) -> int | None:
    cursor = conn.execute("SELECT id FROM tracks WHERE path_norm = ?", (path_norm,))
    row = cursor.fetchone()
    if row is None:
        return None
    return int(row["id"])
