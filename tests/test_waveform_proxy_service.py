"""Tests for lazy cache-first waveform-proxy service behavior."""

from __future__ import annotations

import asyncio

from tz_player.services.waveform_proxy_service import WaveformProxyService
from tz_player.services.waveform_proxy_store import (
    WaveformProxyFrame,
    WaveformProxyParams,
)


class _CacheHitProvider:
    def __init__(self) -> None:
        self.touch_calls = 0

    async def get_frame_at(
        self,
        track_path: str,
        *,
        position_ms: int,
        params: WaveformProxyParams,
    ) -> WaveformProxyFrame | None:
        del track_path, position_ms, params
        return WaveformProxyFrame(
            position_ms=0,
            min_left_i8=-64,
            max_left_i8=96,
            min_right_i8=-48,
            max_right_i8=80,
        )

    async def has_waveform_proxy(
        self, track_path: str, *, params: WaveformProxyParams
    ) -> bool:
        del track_path, params
        return True

    async def touch_waveform_proxy_access(
        self,
        track_path: str,
        *,
        params: WaveformProxyParams,
    ) -> None:
        del track_path, params
        self.touch_calls += 1


class _CacheMissProvider:
    async def get_frame_at(
        self,
        track_path: str,
        *,
        position_ms: int,
        params: WaveformProxyParams,
    ) -> WaveformProxyFrame | None:
        del track_path, position_ms, params
        return None

    async def has_waveform_proxy(
        self, track_path: str, *, params: WaveformProxyParams
    ) -> bool:
        del track_path, params
        return False


def _run(coro):
    return asyncio.run(coro)


def test_waveform_proxy_service_returns_cache_hit_when_available() -> None:
    async def run() -> None:
        provider = _CacheHitProvider()
        service = WaveformProxyService(cache_provider=provider)
        reading = await service.sample(
            track_path="/tmp/song.mp3",
            position_ms=100,
            params=WaveformProxyParams(hop_ms=20),
        )
        assert reading.status == "ready"
        assert reading.source == "cache"
        assert reading.min_left < 0.0
        assert reading.max_left > 0.0
        assert reading.min_right < 0.0
        assert reading.max_right > 0.0
        assert provider.touch_calls == 1

    _run(run())


def test_waveform_proxy_service_throttles_access_touch_updates() -> None:
    async def run() -> None:
        provider = _CacheHitProvider()
        service = WaveformProxyService(cache_provider=provider)
        params = WaveformProxyParams(hop_ms=20)
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


def test_waveform_proxy_service_returns_loading_and_schedules_on_cache_miss() -> None:
    async def run() -> None:
        scheduled: list[tuple[str, WaveformProxyParams]] = []

        async def _schedule(track_path: str, params: WaveformProxyParams) -> None:
            scheduled.append((track_path, params))

        params = WaveformProxyParams(hop_ms=20)
        service = WaveformProxyService(
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
        assert reading.min_left == 0.0
        assert reading.max_right == 0.0
        assert scheduled == [("/tmp/song.mp3", params)]

    _run(run())
