"""Lazy spectrum-service contract and cache-first source selection."""

from __future__ import annotations

import logging
import time
from bisect import bisect_left
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from .spectrum_store import SpectrumFrame, SpectrumParams

SpectrumSource = Literal["cache", "fallback"]
SpectrumStatus = Literal["ready", "loading", "missing", "error"]
logger = logging.getLogger(__name__)


class SpectrumProvider(Protocol):
    """Protocol for persisted spectrum frame lookup by track position."""

    async def get_frame_at(
        self,
        track_path: str,
        *,
        position_ms: int,
        params: SpectrumParams,
    ) -> SpectrumFrame | None: ...

    async def has_spectrum(
        self, track_path: str, *, params: SpectrumParams
    ) -> bool: ...

    async def touch_spectrum_access(
        self, track_path: str, *, params: SpectrumParams
    ) -> None: ...


@dataclass(frozen=True)
class SpectrumReading:
    """Normalized spectrum reading returned to visualizers/services."""

    bands: bytes
    source: SpectrumSource
    status: SpectrumStatus


class SpectrumService:
    """Cache-first lazy spectrum resolver with non-blocking schedule hook."""

    def __init__(
        self,
        *,
        cache_provider: SpectrumProvider,
        schedule_analysis: Callable[[str, SpectrumParams], Awaitable[None]]
        | None = None,
    ) -> None:
        self._cache_provider = cache_provider
        self._schedule_analysis = schedule_analysis
        self._last_touch_s: dict[str, float] = {}
        self._touch_interval_s = 15.0
        self._frame_cache: dict[str, tuple[list[int], list[bytes]]] = {}
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
        params: SpectrumParams,
    ) -> SpectrumReading:
        if not track_path:
            return SpectrumReading(
                bands=b"\x00" * params.band_count,
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
            return SpectrumReading(bands=cached, source="cache", status="ready")

        frame = await self._cache_provider.get_frame_at(
            track_path,
            position_ms=max(0, int(position_ms)),
            params=params,
        )
        if frame is not None:
            await self._touch_access_if_due(track_path, params)
            self._stats_db_hits += 1
            self._maybe_log_stats()
            return SpectrumReading(bands=frame.bands, source="cache", status="ready")

        if self._schedule_analysis is not None:
            await self._schedule_analysis(track_path, params)
            self._stats_loading += 1
            self._maybe_log_stats()
            return SpectrumReading(
                bands=b"\x00" * params.band_count,
                source="fallback",
                status="loading",
            )

        self._stats_misses += 1
        self._maybe_log_stats()
        return SpectrumReading(
            bands=b"\x00" * params.band_count,
            source="fallback",
            status="missing",
        )

    async def preload_track(self, track_path: str, *, params: SpectrumParams) -> int:
        if not track_path:
            return 0
        key = f"{track_path}|{params.band_count}|{params.hop_ms}"
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
        positions = [int(frame.position_ms) for frame in frames]
        bands = [bytes(frame.bands) for frame in frames]
        self._frame_cache.clear()
        self._frame_cache[key] = (positions, bands)
        return len(positions)

    def clear_track_cache(self, track_path: str | None = None) -> None:
        if track_path is None:
            self._frame_cache.clear()
            return
        stale = [key for key in self._frame_cache if key.startswith(f"{track_path}|")]
        for key in stale:
            self._frame_cache.pop(key, None)

    async def _touch_access_if_due(
        self,
        track_path: str,
        params: SpectrumParams,
    ) -> None:
        key = f"{track_path}|{params.band_count}|{params.hop_ms}"
        now = time.monotonic()
        previous = self._last_touch_s.get(key)
        if previous is not None and (now - previous) < self._touch_interval_s:
            return
        touch = getattr(self._cache_provider, "touch_spectrum_access", None)
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
        params: SpectrumParams,
        position_ms: int,
    ) -> bytes | None:
        key = f"{track_path}|{params.band_count}|{params.hop_ms}"
        cached = self._frame_cache.get(key)
        if cached is None:
            return None
        positions, bands = cached
        if not positions:
            return None
        pos = max(0, int(position_ms))
        idx = bisect_left(positions, pos)
        if idx <= 0:
            return bands[0]
        if idx >= len(positions):
            return bands[-1]
        prev_idx = idx - 1
        if (pos - positions[prev_idx]) <= (positions[idx] - pos):
            return bands[prev_idx]
        return bands[idx]

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
            "Spectrum sampling stats",
            extra={
                "event": "spectrum_sampling_stats",
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
