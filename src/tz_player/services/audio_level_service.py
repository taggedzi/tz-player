"""Shared audio-level source selection for sound-reactive visualizers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Protocol

from .playback_backend import LevelSample

LevelSource = Literal["live", "envelope", "fallback"]
PlaybackStatus = Literal["idle", "loading", "playing", "paused", "stopped", "error"]


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


class AudioLevelService:
    """Resolves effective audio levels with deterministic source priority."""

    def __init__(
        self,
        *,
        live_provider: object,
        envelope_provider: EnvelopeLevelProvider | None = None,
    ) -> None:
        self._live_provider = live_provider
        self._envelope_provider = envelope_provider

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
            return AudioLevelReading(
                left=_clamp(live.left),
                right=_clamp(live.right),
                source="live",
            )

        if self._envelope_provider is not None and track_path:
            envelope = await self._sample_envelope(track_path, position_ms)
            if envelope is not None:
                return AudioLevelReading(
                    left=_clamp(envelope.left),
                    right=_clamp(envelope.right),
                    source="envelope",
                )

        left, right = _fallback_levels(
            status=status,
            position_ms=position_ms,
            duration_ms=duration_ms,
            volume=volume,
            speed=speed,
        )
        return AudioLevelReading(left=left, right=right, source="fallback")

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
