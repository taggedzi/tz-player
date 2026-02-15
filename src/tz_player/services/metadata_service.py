"""Async metadata service for track metadata extraction."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from tz_player.services.audio_tags import read_audio_tags
from tz_player.services.playlist_store import (
    PlaylistStore,
    TrackMeta,
    TrackMetaSnapshot,
    TrackRecord,
)
from tz_player.utils.async_utils import run_blocking

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FileStat:
    mtime_ns: int
    size_bytes: int


class MetadataService:
    """Loads track metadata on-demand with bounded concurrency."""

    def __init__(
        self,
        store: PlaylistStore,
        *,
        concurrency: int = 4,
        on_metadata_updated: Callable[[list[int]], Awaitable[None]] | None = None,
    ) -> None:
        if concurrency < 1:
            raise ValueError("MetadataService concurrency must be >= 1.")
        self._store = store
        self._concurrency = concurrency
        self._semaphore: asyncio.Semaphore | None = None
        self._on_metadata_updated = on_metadata_updated

    async def ensure_metadata(self, track_ids: list[int]) -> None:
        unique_ids = _unique_ids(track_ids)
        if not unique_ids:
            return
        tracks = await self._store.get_tracks_basic(unique_ids)
        if not tracks:
            return
        meta_snapshot = await self._store.get_track_meta_snapshot(
            [track.track_id for track in tracks]
        )
        tasks = []
        for track in tracks:
            if _meta_is_fresh(meta_snapshot.get(track.track_id)):
                continue
            tasks.append(asyncio.create_task(self._load_one(track)))
        if not tasks:
            return
        results = await asyncio.gather(*tasks)
        updated_ids = [track_id for track_id, updated in results if updated]
        if updated_ids and self._on_metadata_updated is not None:
            await self._on_metadata_updated(updated_ids)

    async def invalidate_if_changed(self, track_id: int) -> bool:
        records = await self._store.get_tracks_basic([track_id])
        if not records:
            return False
        record = records[0]
        stat = await _safe_stat(record.path)
        if stat is None:
            await self._store.mark_meta_invalid(track_id, "File missing")
            return True
        if record.mtime_ns == stat.mtime_ns and record.size_bytes == stat.size_bytes:
            return False
        snapshot = await self._store.get_track_meta_snapshot([track_id])
        existing = snapshot.get(track_id)
        meta = TrackMeta(
            title=existing.title if existing else None,
            artist=existing.artist if existing else None,
            album=existing.album if existing else None,
            year=existing.year if existing else None,
            duration_ms=existing.duration_ms if existing else None,
            meta_valid=False,
            meta_error="File changed",
            mtime_ns=stat.mtime_ns,
            size_bytes=stat.size_bytes,
        )
        await self._store.upsert_track_meta(track_id, meta)
        return True

    async def _load_one(self, track: TrackRecord) -> tuple[int, bool]:
        semaphore = self._ensure_semaphore()
        async with semaphore:
            stat = await _safe_stat(track.path)
            if stat is None:
                await self._store.upsert_track_meta(
                    track.track_id,
                    TrackMeta(
                        title=None,
                        artist=None,
                        album=None,
                        year=None,
                        duration_ms=None,
                        meta_valid=False,
                        meta_error="File missing",
                        mtime_ns=None,
                        size_bytes=None,
                    ),
                )
                return track.track_id, False
            try:
                payload = await run_blocking(_read_metadata, track.path)
            except Exception as exc:  # pragma: no cover - safety net
                logger.exception("Failed to read metadata for %s: %s", track.path, exc)
                payload = MetadataPayload(error=str(exc))
            meta = TrackMeta(
                title=payload.title or track.path.stem,
                artist=payload.artist,
                album=payload.album,
                year=payload.year,
                duration_ms=payload.duration_ms,
                meta_valid=payload.error is None,
                meta_error=payload.error,
                mtime_ns=stat.mtime_ns,
                size_bytes=stat.size_bytes,
            )
            await self._store.upsert_track_meta(track.track_id, meta)
            return track.track_id, meta.meta_valid

    def _ensure_semaphore(self) -> asyncio.Semaphore:
        semaphore = self._semaphore
        if semaphore is None:
            semaphore = asyncio.Semaphore(self._concurrency)
            self._semaphore = semaphore
        return semaphore


@dataclass(frozen=True)
class MetadataPayload:
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    year: int | None = None
    duration_ms: int | None = None
    error: str | None = None


def _read_metadata(path: Path) -> MetadataPayload:
    tags = read_audio_tags(path)
    return MetadataPayload(
        title=tags.title,
        artist=tags.artist,
        album=tags.album,
        year=tags.year,
        duration_ms=tags.duration_ms,
        error=tags.error,
    )


def _meta_is_fresh(snapshot: TrackMetaSnapshot | None) -> bool:
    if snapshot is None:
        return False
    return snapshot.meta_valid


def _unique_ids(track_ids: list[int]) -> list[int]:
    seen: set[int] = set()
    ordered: list[int] = []
    for track_id in track_ids:
        if track_id in seen:
            continue
        seen.add(track_id)
        ordered.append(track_id)
    return ordered


async def _safe_stat(path: Path) -> FileStat | None:
    try:
        stat = await run_blocking(path.stat)
    except OSError:
        return None
    return FileStat(mtime_ns=stat.st_mtime_ns, size_bytes=stat.st_size)
