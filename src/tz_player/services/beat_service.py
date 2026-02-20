"""Lazy beat-service contract and cache-first source selection."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from .beat_store import BeatFrame, BeatParams

BeatSource = Literal["cache", "fallback"]
BeatStatus = Literal["ready", "loading", "missing", "error"]


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

        frame = await self._cache_provider.get_frame_at(
            track_path,
            position_ms=max(0, int(position_ms)),
            params=params,
        )
        if frame is not None:
            return BeatReading(
                strength=max(0.0, min(1.0, frame.strength_u8 / 255.0)),
                is_beat=frame.is_beat,
                bpm=max(0.0, frame.bpm),
                source="cache",
                status="ready",
            )

        if self._schedule_analysis is not None:
            await self._schedule_analysis(track_path, params)
            return BeatReading(
                strength=0.0,
                is_beat=False,
                bpm=0.0,
                source="fallback",
                status="loading",
            )

        return BeatReading(
            strength=0.0,
            is_beat=False,
            bpm=0.0,
            source="fallback",
            status="missing",
        )
