"""Lazy waveform-proxy service contract and cache-first source selection."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from .waveform_proxy_store import WaveformProxyFrame, WaveformProxyParams

WaveformProxySource = Literal["cache", "fallback"]
WaveformProxyStatus = Literal["ready", "loading", "missing", "error"]


class WaveformProxyProvider(Protocol):
    """Protocol for persisted waveform-proxy frame lookup by track position."""

    async def get_frame_at(
        self,
        track_path: str,
        *,
        position_ms: int,
        params: WaveformProxyParams,
    ) -> WaveformProxyFrame | None: ...

    async def has_waveform_proxy(
        self,
        track_path: str,
        *,
        params: WaveformProxyParams,
    ) -> bool: ...


@dataclass(frozen=True)
class WaveformProxyReading:
    """Normalized waveform-proxy reading returned to visualizers/services."""

    min_left: float
    max_left: float
    min_right: float
    max_right: float
    source: WaveformProxySource
    status: WaveformProxyStatus


class WaveformProxyService:
    """Cache-first lazy waveform-proxy resolver with non-blocking schedule hook."""

    def __init__(
        self,
        *,
        cache_provider: WaveformProxyProvider,
        schedule_analysis: Callable[[str, WaveformProxyParams], Awaitable[None]]
        | None = None,
    ) -> None:
        self._cache_provider = cache_provider
        self._schedule_analysis = schedule_analysis

    async def sample(
        self,
        *,
        track_path: str | None,
        position_ms: int,
        params: WaveformProxyParams,
    ) -> WaveformProxyReading:
        if not track_path:
            return _fallback(status="missing")

        frame = await self._cache_provider.get_frame_at(
            track_path,
            position_ms=max(0, int(position_ms)),
            params=params,
        )
        if frame is not None:
            return WaveformProxyReading(
                min_left=_to_float(frame.min_left_i8),
                max_left=_to_float(frame.max_left_i8),
                min_right=_to_float(frame.min_right_i8),
                max_right=_to_float(frame.max_right_i8),
                source="cache",
                status="ready",
            )

        if self._schedule_analysis is not None:
            await self._schedule_analysis(track_path, params)
            return _fallback(status="loading")

        return _fallback(status="missing")


def _to_float(value: int) -> float:
    return max(-1.0, min(1.0, float(value) / 127.0))


def _fallback(*, status: WaveformProxyStatus) -> WaveformProxyReading:
    return WaveformProxyReading(
        min_left=0.0,
        max_left=0.0,
        min_right=0.0,
        max_right=0.0,
        source="fallback",
        status=status,
    )
