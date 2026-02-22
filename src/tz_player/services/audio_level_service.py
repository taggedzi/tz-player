"""Shared audio-level source selection for sound-reactive visualizers."""

from __future__ import annotations

import logging
import math
import time
from bisect import bisect_left
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from .playback_backend import LevelSample

LevelSource = Literal["live", "envelope", "fallback"]
LevelStatus = Literal["ready", "loading", "missing", "error"]
PlaybackStatus = Literal["idle", "loading", "playing", "paused", "stopped", "error"]
logger = logging.getLogger(__name__)


class EnvelopeLevelProvider(Protocol):
    """Protocol for envelope-backed level sampling by track position."""

    async def get_level_at(
        self, track_path: str, position_ms: int
    ) -> LevelSample | None: ...


@dataclass(frozen=True)
class AudioLevelReading:
    """Normalized stereo reading with source attribution."""

    left: float
    right: float
    source: LevelSource
    status: LevelStatus = "ready"


class AudioLevelService:
    """Resolves effective audio levels with deterministic source priority."""

    def __init__(
        self,
        *,
        live_provider: object,
        envelope_provider: EnvelopeLevelProvider | None = None,
        schedule_envelope_analysis: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self._live_provider = live_provider
        self._envelope_provider = envelope_provider
        self._schedule_envelope_analysis = schedule_envelope_analysis
        self._last_envelope_touch_s: dict[str, float] = {}
        self._envelope_touch_interval_s = 15.0
        self._envelope_cache: dict[
            str, tuple[list[int], list[tuple[float, float]]]
        ] = {}
        self._stats_envelope_memory_hits = 0
        self._stats_envelope_db_hits = 0
        self._stats_fallback_loading = 0
        self._stats_fallback_missing = 0
        self._stats_live_hits = 0
        self._stats_last_log_s = time.monotonic()
        self._stats_log_interval_s = 30.0

    async def sample(
        self,
        *,
        status: PlaybackStatus,
        position_ms: int,
        duration_ms: int,
        volume: int,
        speed: float,
        track_path: str | None,
    ) -> AudioLevelReading | None:
        if status not in {"playing", "paused"}:
            return None

        live = await self._sample_live()
        if live is not None:
            self._stats_live_hits += 1
            self._maybe_log_stats()
            return AudioLevelReading(
                left=_clamp(live.left),
                right=_clamp(live.right),
                source="live",
            )

        if self._envelope_provider is not None and track_path:
            envelope = self._sample_envelope_from_cache(track_path, position_ms)
            from_memory = envelope is not None
            if envelope is None:
                envelope = await self._sample_envelope(track_path, position_ms)
            if envelope is not None:
                await self._touch_envelope_access_if_due(track_path)
                if from_memory:
                    self._stats_envelope_memory_hits += 1
                else:
                    self._stats_envelope_db_hits += 1
                self._maybe_log_stats()
                return AudioLevelReading(
                    left=_clamp(envelope.left),
                    right=_clamp(envelope.right),
                    source="envelope",
                    status="ready",
                )
            if self._schedule_envelope_analysis is not None:
                await self._schedule_envelope_analysis(track_path)
                left, right = _fallback_levels(
                    status=status,
                    position_ms=position_ms,
                    duration_ms=duration_ms,
                    volume=volume,
                    speed=speed,
                )
                self._stats_fallback_loading += 1
                self._maybe_log_stats()
                return AudioLevelReading(
                    left=left,
                    right=right,
                    source="fallback",
                    status="loading",
                )

        left, right = _fallback_levels(
            status=status,
            position_ms=position_ms,
            duration_ms=duration_ms,
            volume=volume,
            speed=speed,
        )
        self._stats_fallback_missing += 1
        self._maybe_log_stats()
        return AudioLevelReading(
            left=left, right=right, source="fallback", status="missing"
        )

    async def _sample_live(self) -> LevelSample | None:
        method = getattr(self._live_provider, "get_level_sample", None)
        if method is None or not callable(method):
            return None
        try:
            return await method()
        except Exception:
            return None

    async def _sample_envelope(
        self, track_path: str, position_ms: int
    ) -> LevelSample | None:
        assert self._envelope_provider is not None
        try:
            return await self._envelope_provider.get_level_at(track_path, position_ms)
        except Exception:
            return None

    async def _touch_envelope_access_if_due(self, track_path: str) -> None:
        if self._envelope_provider is None:
            return
        now = time.monotonic()
        previous = self._last_envelope_touch_s.get(track_path)
        if previous is not None and (now - previous) < self._envelope_touch_interval_s:
            return
        touch = getattr(self._envelope_provider, "touch_envelope_access", None)
        if touch is None or not callable(touch):
            return
        self._last_envelope_touch_s[track_path] = now
        try:
            await touch(track_path)
        except Exception:
            return

    async def preload_envelope_track(self, track_path: str) -> int:
        if not track_path or self._envelope_provider is None:
            return 0
        if track_path in self._envelope_cache:
            return len(self._envelope_cache[track_path][0])
        list_levels = getattr(self._envelope_provider, "list_levels", None)
        if list_levels is None or not callable(list_levels):
            return 0
        try:
            levels = await list_levels(track_path)
        except Exception:
            return 0
        if not levels:
            return 0
        positions = [max(0, int(position_ms)) for position_ms, _left, _right in levels]
        values = [(_clamp(left), _clamp(right)) for _pos, left, right in levels]
        self._envelope_cache.clear()
        self._envelope_cache[track_path] = (positions, values)
        return len(positions)

    def clear_envelope_cache(self, track_path: str | None = None) -> None:
        if track_path is None:
            self._envelope_cache.clear()
            return
        self._envelope_cache.pop(track_path, None)

    def _sample_envelope_from_cache(
        self, track_path: str, position_ms: int
    ) -> LevelSample | None:
        cached = self._envelope_cache.get(track_path)
        if cached is None:
            return None
        positions, values = cached
        if not positions:
            return None
        pos = max(0, int(position_ms))
        idx = bisect_left(positions, pos)
        if idx <= 0:
            left, right = values[0]
            return LevelSample(left=left, right=right)
        if idx >= len(positions):
            left, right = values[-1]
            return LevelSample(left=left, right=right)
        p0 = positions[idx - 1]
        p1 = positions[idx]
        l0, r0 = values[idx - 1]
        l1, r1 = values[idx]
        if p1 <= p0:
            return LevelSample(left=l0, right=r0)
        ratio = (pos - p0) / (p1 - p0)
        return LevelSample(
            left=_clamp(l0 + ((l1 - l0) * ratio)),
            right=_clamp(r0 + ((r1 - r0) * ratio)),
        )

    def _maybe_log_stats(self) -> None:
        now = time.monotonic()
        if (now - self._stats_last_log_s) < self._stats_log_interval_s:
            return
        total = (
            self._stats_live_hits
            + self._stats_envelope_memory_hits
            + self._stats_envelope_db_hits
            + self._stats_fallback_loading
            + self._stats_fallback_missing
        )
        if total <= 0:
            self._stats_last_log_s = now
            return
        logger.info(
            "Audio level sampling stats",
            extra={
                "event": "audio_level_sampling_stats",
                "window_s": round(now - self._stats_last_log_s, 3),
                "live_hits": self._stats_live_hits,
                "envelope_memory_hits": self._stats_envelope_memory_hits,
                "envelope_db_hits": self._stats_envelope_db_hits,
                "fallback_loading": self._stats_fallback_loading,
                "fallback_missing": self._stats_fallback_missing,
                "envelope_memory_hit_rate": round(
                    self._stats_envelope_memory_hits / total, 4
                ),
                "envelope_db_hit_rate": round(self._stats_envelope_db_hits / total, 4),
            },
        )
        self._stats_envelope_memory_hits = 0
        self._stats_envelope_db_hits = 0
        self._stats_fallback_loading = 0
        self._stats_fallback_missing = 0
        self._stats_live_hits = 0
        self._stats_last_log_s = now


def _fallback_levels(
    *,
    status: PlaybackStatus,
    position_ms: int,
    duration_ms: int,
    volume: int,
    speed: float,
) -> tuple[float, float]:
    """Generate deterministic pseudo-reactive fallback levels."""
    if status == "paused" or volume <= 0:
        return (0.0, 0.0)
    base_t = max(0.0, position_ms / 1000.0)
    length_scale = (
        max(0.2, min(2.0, duration_ms / 180_000.0)) if duration_ms > 0 else 1.0
    )
    t = base_t * max(speed, 0.1) / length_scale
    left = 0.10 + 0.70 * (0.30 + 0.70 * (0.5 + 0.5 * math.sin((t * 5.4) + 0.3)))
    right = 0.10 + 0.70 * (0.30 + 0.70 * (0.5 + 0.5 * math.sin((t * 6.1) + 1.2)))
    return (_clamp(left), _clamp(right))


def _clamp(value: float) -> float:
    normalized = float(value)
    if not math.isfinite(normalized):
        return 0.0
    return max(0.0, min(1.0, normalized))
