"""Lazy spectrum-service contract and cache-first source selection."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from .spectrum_store import SpectrumFrame, SpectrumParams

SpectrumSource = Literal["cache", "fallback"]
SpectrumStatus = Literal["ready", "loading", "missing", "error"]


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

        frame = await self._cache_provider.get_frame_at(
            track_path,
            position_ms=max(0, int(position_ms)),
            params=params,
        )
        if frame is not None:
            return SpectrumReading(bands=frame.bands, source="cache", status="ready")

        if self._schedule_analysis is not None:
            await self._schedule_analysis(track_path, params)
            return SpectrumReading(
                bands=b"\x00" * params.band_count,
                source="fallback",
                status="loading",
            )

        return SpectrumReading(
            bands=b"\x00" * params.band_count,
            source="fallback",
            status="missing",
        )
