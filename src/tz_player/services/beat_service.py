"""Lazy beat-service contract and cache-first source selection."""

from __future__ import annotations

import logging
import time
from bisect import bisect_left
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from .beat_store import BeatFrame, BeatParams

BeatSource = Literal["cache", "fallback"]
BeatStatus = Literal["ready", "loading", "missing", "error"]
logger = logging.getLogger(__name__)


class BeatProvider(Protocol):
    """Protocol for persisted beat frame lookup by track position."""

    async def get_frame_at(
        self,
        track_path: str,
        *,
        position_ms: int,
        params: BeatParams,
    ) -> BeatFrame | None: ...

    async def has_beats(self, track_path: str, *, params: BeatParams) -> bool: ...

    async def touch_beat_access(
        self, track_path: str, *, params: BeatParams
    ) -> None: ...


@dataclass(frozen=True)
class BeatReading:
    """Normalized beat reading returned to visualizers/services."""

    strength: float
    is_beat: bool
    bpm: float
    source: BeatSource
    status: BeatStatus


class BeatService:
    """Cache-first lazy beat resolver with non-blocking schedule hook."""

    def __init__(
        self,
        *,
        cache_provider: BeatProvider,
        schedule_analysis: Callable[[str, BeatParams], Awaitable[None]] | None = None,
    ) -> None:
        self._cache_provider = cache_provider
        self._schedule_analysis = schedule_analysis
        self._last_touch_s: dict[str, float] = {}
        self._touch_interval_s = 15.0
        self._frame_cache: dict[str, tuple[list[int], list[BeatFrame]]] = {}
        self._stats_memory_hits = 0
        self._stats_db_hits = 0
        self._stats_misses = 0
        self._stats_loading = 0
        self._stats_last_log_s = time.monotonic()
        self._stats_log_interval_s = 30.0

    async def sample(
        self,
        *,
        track_path: str | None,
        position_ms: int,
        params: BeatParams,
    ) -> BeatReading:
        if not track_path:
            return BeatReading(
                strength=0.0,
                is_beat=False,
                bpm=0.0,
                source="fallback",
                status="missing",
            )

        cached = self._read_from_cache(
            track_path, params=params, position_ms=position_ms
        )
        if cached is not None:
            await self._touch_access_if_due(track_path, params)
            self._stats_memory_hits += 1
            self._maybe_log_stats()
            return BeatReading(
                strength=max(0.0, min(1.0, cached.strength_u8 / 255.0)),
                is_beat=cached.is_beat,
                bpm=max(0.0, cached.bpm),
                source="cache",
                status="ready",
            )

        frame = await self._cache_provider.get_frame_at(
            track_path,
            position_ms=max(0, int(position_ms)),
            params=params,
        )
        if frame is not None:
            await self._touch_access_if_due(track_path, params)
            self._stats_db_hits += 1
            self._maybe_log_stats()
            return BeatReading(
                strength=max(0.0, min(1.0, frame.strength_u8 / 255.0)),
                is_beat=frame.is_beat,
                bpm=max(0.0, frame.bpm),
                source="cache",
                status="ready",
            )

        if self._schedule_analysis is not None:
            await self._schedule_analysis(track_path, params)
            self._stats_loading += 1
            self._maybe_log_stats()
            return BeatReading(
                strength=0.0,
                is_beat=False,
                bpm=0.0,
                source="fallback",
                status="loading",
            )

        self._stats_misses += 1
        self._maybe_log_stats()
        return BeatReading(
            strength=0.0,
            is_beat=False,
            bpm=0.0,
            source="fallback",
            status="missing",
        )

    async def preload_track(self, track_path: str, *, params: BeatParams) -> int:
        if not track_path:
            return 0
        key = f"{track_path}|{params.hop_ms}"
        if key in self._frame_cache:
            return len(self._frame_cache[key][0])
        list_frames = getattr(self._cache_provider, "list_frames", None)
        if list_frames is None or not callable(list_frames):
            return 0
        try:
            frames = await list_frames(track_path, params=params)
        except Exception:
            return 0
        if not frames:
            return 0
        normalized = [
            BeatFrame(
                position_ms=int(frame.position_ms),
                strength_u8=max(0, min(255, int(frame.strength_u8))),
                is_beat=bool(frame.is_beat),
                bpm=max(0.0, float(frame.bpm)),
            )
            for frame in frames
        ]
        self._frame_cache.clear()
        self._frame_cache[key] = (
            [frame.position_ms for frame in normalized],
            normalized,
        )
        return len(normalized)

    def clear_track_cache(self, track_path: str | None = None) -> None:
        if track_path is None:
            self._frame_cache.clear()
            return
        stale = [key for key in self._frame_cache if key.startswith(f"{track_path}|")]
        for key in stale:
            self._frame_cache.pop(key, None)

    async def _touch_access_if_due(self, track_path: str, params: BeatParams) -> None:
        key = f"{track_path}|{params.hop_ms}"
        now = time.monotonic()
        previous = self._last_touch_s.get(key)
        if previous is not None and (now - previous) < self._touch_interval_s:
            return
        touch = getattr(self._cache_provider, "touch_beat_access", None)
        if touch is None or not callable(touch):
            return
        self._last_touch_s[key] = now
        try:
            await touch(track_path, params=params)
        except Exception:
            return

    def _read_from_cache(
        self,
        track_path: str,
        *,
        params: BeatParams,
        position_ms: int,
    ) -> BeatFrame | None:
        key = f"{track_path}|{params.hop_ms}"
        cached = self._frame_cache.get(key)
        if not cached:
            return None
        positions, frames = cached
        pos = max(0, int(position_ms))
        idx = bisect_left(positions, pos)
        if idx <= 0:
            return frames[0]
        if idx >= len(frames):
            return frames[-1]
        prev_idx = idx - 1
        if (pos - positions[prev_idx]) <= (positions[idx] - pos):
            return frames[prev_idx]
        return frames[idx]

    def _maybe_log_stats(self) -> None:
        now = time.monotonic()
        if (now - self._stats_last_log_s) < self._stats_log_interval_s:
            return
        total = (
            self._stats_memory_hits
            + self._stats_db_hits
            + self._stats_loading
            + self._stats_misses
        )
        if total <= 0:
            self._stats_last_log_s = now
            return
        logger.info(
            "Beat sampling stats",
            extra={
                "event": "beat_sampling_stats",
                "window_s": round(now - self._stats_last_log_s, 3),
                "memory_hits": self._stats_memory_hits,
                "db_hits": self._stats_db_hits,
                "loading": self._stats_loading,
                "missing": self._stats_misses,
                "memory_hit_rate": round(self._stats_memory_hits / total, 4),
                "db_hit_rate": round(self._stats_db_hits / total, 4),
            },
        )
        self._stats_memory_hits = 0
        self._stats_db_hits = 0
        self._stats_misses = 0
        self._stats_loading = 0
        self._stats_last_log_s = now
