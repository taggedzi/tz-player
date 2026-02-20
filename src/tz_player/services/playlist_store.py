"""SQLite-backed playlist/query layer for playlist and metadata state.

The public API is async but all DB work is synchronous and dispatched through
`run_blocking(...)` to keep the Textual event loop non-blocking.
"""

from __future__ import annotations

import logging
import os
import random
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tz_player.db.schema import create_schema
from tz_player.utils.async_utils import run_blocking

POS_STEP = 10_000
_PERF_WARN_MS = 50.0
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlaylistRow:
    """Joined playlist row including optional cached metadata fields."""

    item_id: int
    track_id: int
    pos_key: int
    path: Path
    title: str | None
    artist: str | None
    album: str | None
    year: int | None
    duration_ms: int | None
    meta_valid: bool | None
    meta_error: str | None


@dataclass(frozen=True)
class TrackRecord:
    """Minimal immutable track record used for metadata refresh workflows."""

    track_id: int
    path: Path
    mtime_ns: int | None
    size_bytes: int | None


@dataclass(frozen=True)
class TrackMeta:
    """Metadata payload persisted into `track_meta` and mirrored into `tracks`."""

    title: str | None
    artist: str | None
    album: str | None
    year: int | None
    duration_ms: int | None
    meta_valid: bool
    meta_error: str | None
    mtime_ns: int | None
    size_bytes: int | None


@dataclass(frozen=True)
class TrackMetaSnapshot:
    """Read-only metadata snapshot used for change detection."""

    track_id: int
    title: str | None
    artist: str | None
    album: str | None
    year: int | None
    duration_ms: int | None
    meta_valid: bool
    meta_error: str | None


class PlaylistStore:
    """SQLite-backed playlist store with async wrappers.

    Each async call uses a fresh SQLite connection to avoid cross-thread access.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)

    async def initialize(self) -> None:
        await run_blocking(self._initialize_sync)

    async def create_playlist(self, name: str) -> int:
        return await run_blocking(self._create_playlist_sync, name)

    async def ensure_playlist(self, name: str) -> int:
        return await run_blocking(self._ensure_playlist_sync, name)

    async def clear_playlist(self, playlist_id: int) -> None:
        await run_blocking(self._clear_playlist_sync, playlist_id)

    async def add_tracks(self, playlist_id: int, paths: list[Path]) -> int:
        return await run_blocking(self._add_tracks_sync, playlist_id, paths)

    async def remove_items(self, playlist_id: int, item_ids: set[int]) -> int:
        return await run_blocking(self._remove_items_sync, playlist_id, item_ids)

    async def count(self, playlist_id: int) -> int:
        return await run_blocking(self._count_sync, playlist_id)

    async def fetch_window(
        self, playlist_id: int, offset: int, limit: int
    ) -> list[PlaylistRow]:
        return await run_blocking(self._fetch_window_sync, playlist_id, offset, limit)

    async def get_item_row(self, playlist_id: int, item_id: int) -> PlaylistRow | None:
        return await run_blocking(self._get_item_row_sync, playlist_id, item_id)

    async def fetch_rows_by_track_ids(
        self, playlist_id: int, track_ids: list[int]
    ) -> list[PlaylistRow]:
        return await run_blocking(
            self._fetch_rows_by_track_ids_sync, playlist_id, track_ids
        )

    async def fetch_rows_by_item_ids(
        self, playlist_id: int, item_ids: list[int]
    ) -> list[PlaylistRow]:
        return await run_blocking(
            self._fetch_rows_by_item_ids_sync, playlist_id, item_ids
        )

    async def search_item_ids(
        self, playlist_id: int, query: str, *, limit: int = 1000
    ) -> list[int]:
        return await run_blocking(self._search_item_ids_sync, playlist_id, query, limit)

    async def get_next_item_id(
        self, playlist_id: int, item_id: int, *, wrap: bool
    ) -> int | None:
        return await run_blocking(
            self._get_next_item_id_sync, playlist_id, item_id, wrap
        )

    async def get_prev_item_id(
        self, playlist_id: int, item_id: int, *, wrap: bool
    ) -> int | None:
        return await run_blocking(
            self._get_prev_item_id_sync, playlist_id, item_id, wrap
        )

    async def move_selection(
        self,
        playlist_id: int,
        direction: Literal["up", "down"],
        selection: list[int],
        cursor: int | None,
    ) -> None:
        if direction not in {"up", "down"}:
            raise ValueError("direction must be 'up' or 'down'")
        await run_blocking(
            self._move_selection_sync, playlist_id, direction, selection, cursor
        )

    async def invalidate_metadata(self, track_ids: set[int] | None = None) -> None:
        await run_blocking(self._invalidate_metadata_sync, track_ids)

    async def renumber_playlist(self, playlist_id: int) -> None:
        await run_blocking(self._renumber_playlist_sync, playlist_id)

    async def get_track_id_for_item(self, playlist_id: int, item_id: int) -> int | None:
        return await run_blocking(
            self._get_track_id_for_item_sync, playlist_id, item_id
        )

    async def get_item_index(self, playlist_id: int, item_id: int) -> int | None:
        return await run_blocking(self._get_item_index_sync, playlist_id, item_id)

    async def list_item_ids(self, playlist_id: int) -> list[int]:
        return await run_blocking(self._list_item_ids_sync, playlist_id)

    async def get_random_item_id(
        self, playlist_id: int, *, exclude_item_id: int | None = None
    ) -> int | None:
        return await run_blocking(
            self._get_random_item_id_sync, playlist_id, exclude_item_id
        )

    async def get_tracks_basic(self, track_ids: list[int]) -> list[TrackRecord]:
        return await run_blocking(self._get_tracks_basic_sync, track_ids)

    async def get_track_meta_snapshot(
        self, track_ids: list[int]
    ) -> dict[int, TrackMetaSnapshot]:
        return await run_blocking(self._get_track_meta_snapshot_sync, track_ids)

    async def upsert_track_meta(self, track_id: int, meta: TrackMeta) -> None:
        await run_blocking(self._upsert_track_meta_sync, track_id, meta)

    async def mark_meta_invalid(self, track_id: int, error: str | None = None) -> None:
        await run_blocking(self._mark_meta_invalid_sync, track_id, error)

    def _connect(self) -> sqlite3.Connection:
        """Create a fresh SQLite connection configured for concurrent app usage."""
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
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "DELETE FROM playlist_items WHERE playlist_id = ?", (playlist_id,)
            )

    def _add_tracks_sync(self, playlist_id: int, paths: list[Path]) -> int:
        """Insert track references and append playlist items in stable order."""
        if not paths:
            return 0

        start = time.perf_counter()
        added = 0
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                "SELECT COALESCE(MAX(pos_key), 0) FROM playlist_items WHERE playlist_id = ?",
                (playlist_id,),
            )
            next_pos = int(cursor.fetchone()[0]) + POS_STEP
            # `pos_key` spacing allows cheap local reorders without global renumber.
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
        _log_slow_db_op(
            "add_tracks",
            start=start,
            playlist_id=playlist_id,
            requested=len(paths),
            added=added,
        )
        return added

    def _remove_items_sync(self, playlist_id: int, item_ids: set[int]) -> int:
        if not item_ids:
            return 0
        placeholders = ", ".join("?" for _ in item_ids)
        params: list[int] = [playlist_id, *item_ids]
        with self._connect() as conn:
            cursor = conn.execute(
                f"""
                DELETE FROM playlist_items
                WHERE playlist_id = ? AND id IN ({placeholders})
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
        start = time.perf_counter()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    playlist_items.id AS item_id,
                    playlist_items.track_id,
                    playlist_items.pos_key,
                    tracks.path,
                    track_meta.title,
                    track_meta.artist,
                    track_meta.album,
                    track_meta.year,
                    track_meta.duration_ms,
                    track_meta.meta_valid,
                    track_meta.meta_error
                FROM playlist_items
                JOIN tracks ON tracks.id = playlist_items.track_id
                LEFT JOIN track_meta ON track_meta.track_id = tracks.id
                WHERE playlist_items.playlist_id = ?
                ORDER BY playlist_items.pos_key
                LIMIT ? OFFSET ?
                """,
                (playlist_id, limit, offset),
            ).fetchall()
        result = [
            PlaylistRow(
                item_id=int(row["item_id"]),
                track_id=int(row["track_id"]),
                pos_key=int(row["pos_key"]),
                path=Path(row["path"]),
                title=row["title"],
                artist=row["artist"],
                album=row["album"],
                year=row["year"],
                duration_ms=row["duration_ms"],
                meta_valid=_coerce_meta_valid(row["meta_valid"]),
                meta_error=row["meta_error"],
            )
            for row in rows
        ]
        _log_slow_db_op(
            "fetch_window",
            start=start,
            playlist_id=playlist_id,
            offset=offset,
            limit=limit,
            rows=len(result),
        )
        return result

    def _get_item_row_sync(self, playlist_id: int, item_id: int) -> PlaylistRow | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    playlist_items.id AS item_id,
                    playlist_items.track_id,
                    playlist_items.pos_key,
                    tracks.path,
                    track_meta.title,
                    track_meta.artist,
                    track_meta.album,
                    track_meta.year,
                    track_meta.duration_ms,
                    track_meta.meta_valid,
                    track_meta.meta_error
                FROM playlist_items
                JOIN tracks ON tracks.id = playlist_items.track_id
                LEFT JOIN track_meta ON track_meta.track_id = tracks.id
                WHERE playlist_items.playlist_id = ? AND playlist_items.id = ?
                LIMIT 1
                """,
                (playlist_id, item_id),
            ).fetchone()
        if row is None:
            return None
        return PlaylistRow(
            item_id=int(row["item_id"]),
            track_id=int(row["track_id"]),
            pos_key=int(row["pos_key"]),
            path=Path(row["path"]),
            title=row["title"],
            artist=row["artist"],
            album=row["album"],
            year=row["year"],
            duration_ms=row["duration_ms"],
            meta_valid=_coerce_meta_valid(row["meta_valid"]),
            meta_error=row["meta_error"],
        )

    def _fetch_rows_by_track_ids_sync(
        self, playlist_id: int, track_ids: list[int]
    ) -> list[PlaylistRow]:
        if not track_ids:
            return []
        placeholders = ", ".join("?" for _ in track_ids)
        params: list[int] = [playlist_id, *track_ids]
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    playlist_items.id AS item_id,
                    playlist_items.track_id,
                    playlist_items.pos_key,
                    tracks.path,
                    track_meta.title,
                    track_meta.artist,
                    track_meta.album,
                    track_meta.year,
                    track_meta.duration_ms,
                    track_meta.meta_valid,
                    track_meta.meta_error
                FROM playlist_items
                JOIN tracks ON tracks.id = playlist_items.track_id
                LEFT JOIN track_meta ON track_meta.track_id = tracks.id
                WHERE playlist_items.playlist_id = ?
                  AND playlist_items.track_id IN ({placeholders})
                ORDER BY playlist_items.pos_key
                """,
                params,
            ).fetchall()
        return [
            PlaylistRow(
                item_id=int(row["item_id"]),
                track_id=int(row["track_id"]),
                pos_key=int(row["pos_key"]),
                path=Path(row["path"]),
                title=row["title"],
                artist=row["artist"],
                album=row["album"],
                year=row["year"],
                duration_ms=row["duration_ms"],
                meta_valid=_coerce_meta_valid(row["meta_valid"]),
                meta_error=row["meta_error"],
            )
            for row in rows
        ]

    def _fetch_rows_by_item_ids_sync(
        self, playlist_id: int, item_ids: list[int]
    ) -> list[PlaylistRow]:
        if not item_ids:
            return []
        placeholders = ", ".join("?" for _ in item_ids)
        order_cases = " ".join(
            f"WHEN playlist_items.id = ? THEN {idx}" for idx in range(len(item_ids))
        )
        params: list[int] = [playlist_id, *item_ids, *item_ids]
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    playlist_items.id AS item_id,
                    playlist_items.track_id,
                    playlist_items.pos_key,
                    tracks.path,
                    track_meta.title,
                    track_meta.artist,
                    track_meta.album,
                    track_meta.year,
                    track_meta.duration_ms,
                    track_meta.meta_valid,
                    track_meta.meta_error
                FROM playlist_items
                JOIN tracks ON tracks.id = playlist_items.track_id
                LEFT JOIN track_meta ON track_meta.track_id = tracks.id
                WHERE playlist_items.playlist_id = ?
                  AND playlist_items.id IN ({placeholders})
                ORDER BY CASE {order_cases} END
                """,
                params,
            ).fetchall()
        return [
            PlaylistRow(
                item_id=int(row["item_id"]),
                track_id=int(row["track_id"]),
                pos_key=int(row["pos_key"]),
                path=Path(row["path"]),
                title=row["title"],
                artist=row["artist"],
                album=row["album"],
                year=row["year"],
                duration_ms=row["duration_ms"],
                meta_valid=_coerce_meta_valid(row["meta_valid"]),
                meta_error=row["meta_error"],
            )
            for row in rows
        ]

    def _search_item_ids_sync(
        self, playlist_id: int, query: str, limit: int
    ) -> list[int]:
        """Search playlist rows by tokenized AND matching across metadata/path."""
        start = time.perf_counter()
        tokens = [token.strip().lower() for token in query.split() if token.strip()]
        if not tokens:
            return []
        field_exprs = [
            "LOWER(COALESCE(track_meta.title, ''))",
            "LOWER(COALESCE(track_meta.artist, ''))",
            "LOWER(COALESCE(track_meta.album, ''))",
            "LOWER(COALESCE(CAST(track_meta.year AS TEXT), ''))",
            "LOWER(COALESCE(tracks.path, ''))",
        ]
        token_clauses = []
        for _ in tokens:
            token_clauses.append(
                "(" + " OR ".join(f"{expr} LIKE ?" for expr in field_exprs) + ")"
            )
        where_clause = " AND ".join(token_clauses)
        params: list[object] = [playlist_id]
        for token in tokens:
            params.extend([f"%{token}%"] * len(field_exprs))
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT playlist_items.id AS item_id
                FROM playlist_items
                JOIN tracks ON tracks.id = playlist_items.track_id
                LEFT JOIN track_meta ON track_meta.track_id = tracks.id
                WHERE playlist_items.playlist_id = ?
                  AND {where_clause}
                ORDER BY playlist_items.pos_key
                LIMIT ?
                """,
                params,
            ).fetchall()
        result = [int(row["item_id"]) for row in rows]
        _log_slow_db_op(
            "search_item_ids",
            start=start,
            playlist_id=playlist_id,
            token_count=len(tokens),
            limit=limit,
            rows=len(result),
        )
        return result

    def _get_next_item_id_sync(
        self, playlist_id: int, item_id: int, wrap: bool
    ) -> int | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT pos_key
                FROM playlist_items
                WHERE playlist_id = ? AND id = ?
                """,
                (playlist_id, item_id),
            ).fetchone()
            if row is None:
                return None
            pos_key = int(row["pos_key"])
            next_row = conn.execute(
                """
                SELECT id
                FROM playlist_items
                WHERE playlist_id = ? AND pos_key > ?
                ORDER BY pos_key ASC
                LIMIT 1
                """,
                (playlist_id, pos_key),
            ).fetchone()
            if next_row is not None:
                return int(next_row["id"])
            if not wrap:
                return None
            wrap_row = conn.execute(
                """
                SELECT id
                FROM playlist_items
                WHERE playlist_id = ?
                ORDER BY pos_key ASC
                LIMIT 1
                """,
                (playlist_id,),
            ).fetchone()
            if wrap_row is None:
                return None
            return int(wrap_row["id"])

    def _get_prev_item_id_sync(
        self, playlist_id: int, item_id: int, wrap: bool
    ) -> int | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT pos_key
                FROM playlist_items
                WHERE playlist_id = ? AND id = ?
                """,
                (playlist_id, item_id),
            ).fetchone()
            if row is None:
                return None
            pos_key = int(row["pos_key"])
            prev_row = conn.execute(
                """
                SELECT id
                FROM playlist_items
                WHERE playlist_id = ? AND pos_key < ?
                ORDER BY pos_key DESC
                LIMIT 1
                """,
                (playlist_id, pos_key),
            ).fetchone()
            if prev_row is not None:
                return int(prev_row["id"])
            if not wrap:
                return None
            wrap_row = conn.execute(
                """
                SELECT id
                FROM playlist_items
                WHERE playlist_id = ?
                ORDER BY pos_key DESC
                LIMIT 1
                """,
                (playlist_id,),
            ).fetchone()
            if wrap_row is None:
                return None
            return int(wrap_row["id"])

    def _move_selection_sync(
        self,
        playlist_id: int,
        direction: Literal["up", "down"],
        selection: list[int],
        cursor: int | None,
    ) -> None:
        """Reorder selected items one step while preserving relative block order."""
        if not selection and cursor is None:
            return
        selection_ids = set(selection or ([cursor] if cursor is not None else []))
        if not selection_ids:
            return

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """
                SELECT id, pos_key
                FROM playlist_items
                WHERE playlist_id = ?
                ORDER BY pos_key
                """,
                (playlist_id,),
            ).fetchall()
            if not rows:
                return
            item_ids = [int(row["id"]) for row in rows]
            pos_keys = [int(row["pos_key"]) for row in rows]

            if direction == "up":
                # Scan top->bottom so each selected row swaps at most once.
                for index in range(1, len(item_ids)):
                    if (
                        item_ids[index] in selection_ids
                        and item_ids[index - 1] not in selection_ids
                    ):
                        item_ids[index - 1], item_ids[index] = (
                            item_ids[index],
                            item_ids[index - 1],
                        )
            else:
                # Scan bottom->top for symmetric one-step downward moves.
                for index in range(len(item_ids) - 2, -1, -1):
                    if (
                        item_ids[index] in selection_ids
                        and item_ids[index + 1] not in selection_ids
                    ):
                        item_ids[index + 1], item_ids[index] = (
                            item_ids[index],
                            item_ids[index + 1],
                        )

            updates = [
                (pos_keys[i], playlist_id, item_ids[i]) for i in range(len(item_ids))
            ]
            conn.executemany(
                """
                UPDATE playlist_items
                SET pos_key = ?
                WHERE playlist_id = ? AND id = ?
                """,
                updates,
            )

    def _get_track_id_for_item_sync(self, playlist_id: int, item_id: int) -> int | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT track_id
                FROM playlist_items
                WHERE playlist_id = ? AND id = ?
                """,
                (playlist_id, item_id),
            ).fetchone()
        if row is None:
            return None
        return int(row["track_id"])

    def _get_item_index_sync(self, playlist_id: int, item_id: int) -> int | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT pos_key
                FROM playlist_items
                WHERE playlist_id = ? AND id = ?
                """,
                (playlist_id, item_id),
            ).fetchone()
            if row is None:
                return None
            pos_key = int(row["pos_key"])
            count_row = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM playlist_items
                WHERE playlist_id = ? AND pos_key <= ?
                """,
                (playlist_id, pos_key),
            ).fetchone()
        if count_row is None:
            return None
        return int(count_row["count"])

    def _list_item_ids_sync(self, playlist_id: int) -> list[int]:
        start = time.perf_counter()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id
                FROM playlist_items
                WHERE playlist_id = ?
                ORDER BY pos_key ASC
                """,
                (playlist_id,),
            ).fetchall()
        result = [int(row["id"]) for row in rows]
        _log_slow_db_op(
            "list_item_ids",
            start=start,
            playlist_id=playlist_id,
            rows=len(result),
        )
        return result

    def _get_random_item_id_sync(
        self, playlist_id: int, exclude_item_id: int | None
    ) -> int | None:
        start = time.perf_counter()
        with self._connect() as conn:
            if exclude_item_id is None:
                count_row = conn.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM playlist_items
                    WHERE playlist_id = ?
                    """,
                    (playlist_id,),
                ).fetchone()
                total = int(count_row["count"]) if count_row is not None else 0
                if total <= 0:
                    return None
                random_offset = random.randrange(total)
                row = conn.execute(
                    """
                    SELECT id
                    FROM playlist_items
                    WHERE playlist_id = ?
                    ORDER BY pos_key ASC
                    LIMIT 1 OFFSET ?
                    """,
                    (playlist_id, random_offset),
                ).fetchone()
            else:
                count_row = conn.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM playlist_items
                    WHERE playlist_id = ? AND id != ?
                    """,
                    (playlist_id, exclude_item_id),
                ).fetchone()
                total = int(count_row["count"]) if count_row is not None else 0
                if total <= 0:
                    return None
                random_offset = random.randrange(total)
                row = conn.execute(
                    """
                    SELECT id
                    FROM playlist_items
                    WHERE playlist_id = ? AND id != ?
                    ORDER BY pos_key ASC
                    LIMIT 1 OFFSET ?
                    """,
                    (playlist_id, exclude_item_id, random_offset),
                ).fetchone()
        if row is None:
            return None
        result = int(row["id"])
        _log_slow_db_op(
            "get_random_item_id",
            start=start,
            playlist_id=playlist_id,
            excluded=exclude_item_id,
            selected=result,
        )
        return result

    def _invalidate_metadata_sync(self, track_ids: set[int] | None) -> None:
        with self._connect() as conn:
            if not track_ids:
                conn.execute("UPDATE track_meta SET meta_valid = 0, meta_error = NULL")
                return
            placeholders = ", ".join("?" for _ in track_ids)
            conn.execute(
                f"""
                UPDATE track_meta
                SET meta_valid = 0, meta_error = NULL
                WHERE track_id IN ({placeholders})
                """,
                list(track_ids),
            )

    def _renumber_playlist_sync(self, playlist_id: int) -> None:
        """Compact `pos_key` values back to evenly spaced increments."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """
                SELECT id
                FROM playlist_items
                WHERE playlist_id = ?
                ORDER BY pos_key
                """,
                (playlist_id,),
            ).fetchall()
            updates = []
            next_pos = POS_STEP
            for row in rows:
                updates.append((next_pos, playlist_id, int(row["id"])))
                next_pos += POS_STEP
            conn.executemany(
                """
                UPDATE playlist_items
                SET pos_key = ?
                WHERE playlist_id = ? AND id = ?
                """,
                updates,
            )

    def _get_tracks_basic_sync(self, track_ids: list[int]) -> list[TrackRecord]:
        if not track_ids:
            return []
        placeholders = ", ".join("?" for _ in track_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, path, mtime_ns, size_bytes
                FROM tracks
                WHERE id IN ({placeholders})
                """,
                track_ids,
            ).fetchall()
        return [
            TrackRecord(
                track_id=int(row["id"]),
                path=Path(row["path"]),
                mtime_ns=row["mtime_ns"],
                size_bytes=row["size_bytes"],
            )
            for row in rows
        ]

    def _get_track_meta_snapshot_sync(
        self, track_ids: list[int]
    ) -> dict[int, TrackMetaSnapshot]:
        if not track_ids:
            return {}
        placeholders = ", ".join("?" for _ in track_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT track_id, title, artist, album, year, duration_ms, meta_valid, meta_error
                FROM track_meta
                WHERE track_id IN ({placeholders})
                """,
                track_ids,
            ).fetchall()
        snapshots = {}
        for row in rows:
            track_id = int(row["track_id"])
            snapshots[track_id] = TrackMetaSnapshot(
                track_id=track_id,
                title=row["title"],
                artist=row["artist"],
                album=row["album"],
                year=row["year"],
                duration_ms=row["duration_ms"],
                meta_valid=bool(row["meta_valid"]),
                meta_error=row["meta_error"],
            )
        return snapshots

    def _upsert_track_meta_sync(self, track_id: int, meta: TrackMeta) -> None:
        now = int(time.time())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT INTO track_meta (
                    track_id,
                    title,
                    artist,
                    album,
                    year,
                    duration_ms,
                    meta_loaded_at,
                    meta_valid,
                    meta_error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(track_id) DO UPDATE SET
                    title = excluded.title,
                    artist = excluded.artist,
                    album = excluded.album,
                    year = excluded.year,
                    duration_ms = excluded.duration_ms,
                    meta_loaded_at = excluded.meta_loaded_at,
                    meta_valid = excluded.meta_valid,
                    meta_error = excluded.meta_error
                """,
                (
                    track_id,
                    meta.title,
                    meta.artist,
                    meta.album,
                    meta.year,
                    meta.duration_ms,
                    now,
                    int(meta.meta_valid),
                    meta.meta_error,
                ),
            )
            conn.execute(
                """
                UPDATE tracks
                SET mtime_ns = ?, size_bytes = ?, updated_at = ?
                WHERE id = ?
                """,
                (meta.mtime_ns, meta.size_bytes, now, track_id),
            )

    def _mark_meta_invalid_sync(self, track_id: int, error: str | None) -> None:
        now = int(time.time())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT INTO track_meta (
                    track_id,
                    meta_loaded_at,
                    meta_valid,
                    meta_error
                )
                VALUES (?, ?, 0, ?)
                ON CONFLICT(track_id) DO UPDATE SET
                    meta_loaded_at = excluded.meta_loaded_at,
                    meta_valid = excluded.meta_valid,
                    meta_error = excluded.meta_error
                """,
                (track_id, now, error),
            )
            conn.execute(
                "UPDATE tracks SET updated_at = ? WHERE id = ?",
                (now, track_id),
            )


def _normalize_path(path: Path) -> str:
    """Normalize paths for uniqueness checks across case/relative variants."""
    return os.path.normcase(str(path.expanduser().resolve(strict=False)))


def _stat_path(path: Path) -> tuple[int | None, int | None]:
    try:
        stat = path.stat()
    except OSError:
        return None, None
    return stat.st_mtime_ns, stat.st_size


def _coerce_meta_valid(value: int | None) -> bool | None:
    if value is None:
        return None
    return bool(int(value))


def _log_slow_db_op(op: str, *, start: float, **context: object) -> None:
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    if elapsed_ms < _PERF_WARN_MS:
        return
    logger.info(
        "PlaylistStore operation exceeded perf threshold",
        extra={
            "event": "playlist_store_slow_query",
            "operation": op,
            "elapsed_ms": round(elapsed_ms, 2),
            **context,
        },
    )


def _get_track_id(conn: sqlite3.Connection, path_norm: str) -> int | None:
    cursor = conn.execute("SELECT id FROM tracks WHERE path_norm = ?", (path_norm,))
    row = cursor.fetchone()
    if row is None:
        return None
    return int(row["id"])
