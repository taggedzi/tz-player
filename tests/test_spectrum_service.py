"""Tests for lazy cache-first spectrum service behavior."""

from __future__ import annotations

import asyncio

from tz_player.services.spectrum_service import SpectrumService
from tz_player.services.spectrum_store import SpectrumFrame, SpectrumParams


class _CacheHitProvider:
    def __init__(self) -> None:
        self.touch_calls = 0

    async def get_frame_at(
        self,
        track_path: str,
        *,
        position_ms: int,
        params: SpectrumParams,
    ) -> SpectrumFrame | None:
        del track_path, position_ms, params
        return SpectrumFrame(position_ms=0, bands=bytes([1, 2, 3, 4]))

    async def has_spectrum(self, track_path: str, *, params: SpectrumParams) -> bool:
        del track_path, params
        return True

    async def touch_spectrum_access(
        self, track_path: str, *, params: SpectrumParams
    ) -> None:
        del track_path, params
        self.touch_calls += 1


class _CacheMissProvider:
    async def get_frame_at(
        self,
        track_path: str,
        *,
        position_ms: int,
        params: SpectrumParams,
    ) -> SpectrumFrame | None:
        del track_path, position_ms, params
        return None

    async def has_spectrum(self, track_path: str, *, params: SpectrumParams) -> bool:
        del track_path, params
        return False


def _run(coro):
    return asyncio.run(coro)


def test_spectrum_service_returns_cache_hit_when_available() -> None:
    async def run() -> None:
        provider = _CacheHitProvider()
        service = SpectrumService(cache_provider=provider)
        reading = await service.sample(
            track_path="/tmp/song.mp3",
            position_ms=100,
            params=SpectrumParams(band_count=4, hop_ms=40),
        )
        assert reading.status == "ready"
        assert reading.source == "cache"
        assert reading.bands == bytes([1, 2, 3, 4])
        assert provider.touch_calls == 1

    _run(run())


def test_spectrum_service_throttles_access_touch_updates() -> None:
    async def run() -> None:
        provider = _CacheHitProvider()
        service = SpectrumService(cache_provider=provider)
        params = SpectrumParams(band_count=4, hop_ms=40)
        await service.sample(
            track_path="/tmp/song.mp3",
            position_ms=10,
            params=params,
        )
        await service.sample(
            track_path="/tmp/song.mp3",
            position_ms=20,
            params=params,
        )
        assert provider.touch_calls == 1

    _run(run())


def test_spectrum_service_returns_loading_and_schedules_on_cache_miss() -> None:
    async def run() -> None:
        scheduled: list[tuple[str, SpectrumParams]] = []

        async def _schedule(track_path: str, params: SpectrumParams) -> None:
            scheduled.append((track_path, params))

        params = SpectrumParams(band_count=4, hop_ms=40)
        service = SpectrumService(
            cache_provider=_CacheMissProvider(),
            schedule_analysis=_schedule,
        )
        reading = await service.sample(
            track_path="/tmp/song.mp3",
            position_ms=100,
            params=params,
        )
        assert reading.status == "loading"
        assert reading.source == "fallback"
        assert reading.bands == bytes([0, 0, 0, 0])
        assert scheduled == [("/tmp/song.mp3", params)]

    _run(run())
