"""Tests for lazy cache-first beat service behavior."""

from __future__ import annotations

import asyncio

from tz_player.services.beat_service import BeatService
from tz_player.services.beat_store import BeatFrame, BeatParams


class _CacheHitProvider:
    def __init__(self) -> None:
        self.touch_calls = 0

    async def get_frame_at(
        self,
        track_path: str,
        *,
        position_ms: int,
        params: BeatParams,
    ) -> BeatFrame | None:
        del track_path, position_ms, params
        return BeatFrame(position_ms=0, strength_u8=128, is_beat=True, bpm=120.0)

    async def has_beats(self, track_path: str, *, params: BeatParams) -> bool:
        del track_path, params
        return True

    async def touch_beat_access(self, track_path: str, *, params: BeatParams) -> None:
        del track_path, params
        self.touch_calls += 1


class _CacheMissProvider:
    async def get_frame_at(
        self,
        track_path: str,
        *,
        position_ms: int,
        params: BeatParams,
    ) -> BeatFrame | None:
        del track_path, position_ms, params
        return None

    async def has_beats(self, track_path: str, *, params: BeatParams) -> bool:
        del track_path, params
        return False


def _run(coro):
    return asyncio.run(coro)


def test_beat_service_returns_cache_hit_when_available() -> None:
    async def run() -> None:
        provider = _CacheHitProvider()
        service = BeatService(cache_provider=provider)
        reading = await service.sample(
            track_path="/tmp/song.mp3",
            position_ms=100,
            params=BeatParams(hop_ms=40),
        )
        assert reading.status == "ready"
        assert reading.source == "cache"
        assert reading.is_beat is True
        assert reading.bpm == 120.0
        assert 0.49 < reading.strength < 0.51
        assert provider.touch_calls == 1

    _run(run())


def test_beat_service_throttles_access_touch_updates() -> None:
    async def run() -> None:
        provider = _CacheHitProvider()
        service = BeatService(cache_provider=provider)
        params = BeatParams(hop_ms=40)
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


def test_beat_service_returns_loading_and_schedules_on_cache_miss() -> None:
    async def run() -> None:
        scheduled: list[tuple[str, BeatParams]] = []

        async def _schedule(track_path: str, params: BeatParams) -> None:
            scheduled.append((track_path, params))

        params = BeatParams(hop_ms=40)
        service = BeatService(
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
        assert reading.strength == 0.0
        assert reading.is_beat is False
        assert reading.bpm == 0.0
        assert scheduled == [("/tmp/song.mp3", params)]

    _run(run())
