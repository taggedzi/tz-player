"""Tests for shared audio level service source selection."""

from __future__ import annotations

import asyncio

from tz_player.services.audio_level_service import AudioLevelService
from tz_player.services.playback_backend import LevelSample


class _LiveProvider:
    async def get_level_sample(self) -> LevelSample | None:
        return LevelSample(left=0.9, right=0.6)


class _NoLiveProvider:
    async def get_level_sample(self) -> LevelSample | None:
        return None


class _EnvelopeProvider:
    async def get_level_at(
        self, track_path: str, position_ms: int
    ) -> LevelSample | None:
        del track_path, position_ms
        return LevelSample(left=0.4, right=0.5)


def _run(coro):
    return asyncio.run(coro)


def test_audio_level_service_prefers_live_source() -> None:
    async def run() -> None:
        service = AudioLevelService(
            live_provider=_LiveProvider(),
            envelope_provider=_EnvelopeProvider(),
        )
        reading = await service.sample(
            status="playing",
            position_ms=1000,
            duration_ms=5000,
            volume=60,
            speed=1.0,
            track_path="/tmp/song.mp3",
        )
        assert reading is not None
        assert reading.source == "live"
        assert 0.0 <= reading.left <= 1.0
        assert 0.0 <= reading.right <= 1.0

    _run(run())


def test_audio_level_service_uses_envelope_when_live_unavailable() -> None:
    async def run() -> None:
        service = AudioLevelService(
            live_provider=_NoLiveProvider(),
            envelope_provider=_EnvelopeProvider(),
        )
        reading = await service.sample(
            status="playing",
            position_ms=1000,
            duration_ms=5000,
            volume=60,
            speed=1.0,
            track_path="/tmp/song.mp3",
        )
        assert reading is not None
        assert reading.source == "envelope"
        assert reading.left == 0.4
        assert reading.right == 0.5

    _run(run())


def test_audio_level_service_uses_fallback_when_no_live_or_envelope() -> None:
    async def run() -> None:
        service = AudioLevelService(live_provider=_NoLiveProvider())
        reading = await service.sample(
            status="playing",
            position_ms=1000,
            duration_ms=5000,
            volume=60,
            speed=1.0,
            track_path="/tmp/song.mp3",
        )
        assert reading is not None
        assert reading.source == "fallback"
        assert 0.0 <= reading.left <= 1.0
        assert 0.0 <= reading.right <= 1.0

    _run(run())


def test_audio_level_service_returns_none_when_not_playing_or_paused() -> None:
    async def run() -> None:
        service = AudioLevelService(live_provider=_NoLiveProvider())
        reading = await service.sample(
            status="stopped",
            position_ms=1000,
            duration_ms=5000,
            volume=60,
            speed=1.0,
            track_path="/tmp/song.mp3",
        )
        assert reading is None

    _run(run())
