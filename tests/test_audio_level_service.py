"""Tests for shared audio level service source selection."""

from __future__ import annotations

import asyncio

from tz_player.services.audio_level_service import AudioLevelService
from tz_player.services.playback_backend import LevelSample


class _LiveProvider:
    """Live-level provider stub returning finite sample values."""

    async def get_level_sample(self) -> LevelSample | None:
        return LevelSample(left=0.9, right=0.6)


class _NoLiveProvider:
    """Live-level provider stub that simulates unavailable samples."""

    async def get_level_sample(self) -> LevelSample | None:
        return None


class _EnvelopeProvider:
    """Envelope provider stub returning deterministic cached levels."""

    def __init__(self) -> None:
        self.touch_calls = 0

    async def get_level_at(
        self, track_path: str, position_ms: int
    ) -> LevelSample | None:
        del track_path, position_ms
        return LevelSample(left=0.4, right=0.5)

    async def touch_envelope_access(self, track_path: str) -> None:
        del track_path
        self.touch_calls += 1


class _MissingEnvelopeProvider:
    """Envelope provider stub that simulates cache miss."""

    async def get_level_at(
        self, track_path: str, position_ms: int
    ) -> LevelSample | None:
        del track_path, position_ms
        return None


class _NonFiniteLiveProvider:
    """Live provider stub returning non-finite levels for sanitization tests."""

    async def get_level_sample(self) -> LevelSample | None:
        return LevelSample(left=float("nan"), right=float("inf"))


def _run(coro):
    """Run async level-service scenario from sync test function."""
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
        assert reading.status == "ready"

    _run(run())


def test_audio_level_service_uses_envelope_when_live_unavailable() -> None:
    async def run() -> None:
        envelope_provider = _EnvelopeProvider()
        service = AudioLevelService(
            live_provider=_NoLiveProvider(),
            envelope_provider=envelope_provider,
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
        assert reading.status == "ready"
        assert envelope_provider.touch_calls == 1

    _run(run())


def test_audio_level_service_throttles_envelope_access_touches() -> None:
    async def run() -> None:
        envelope_provider = _EnvelopeProvider()
        service = AudioLevelService(
            live_provider=_NoLiveProvider(),
            envelope_provider=envelope_provider,
        )
        for position_ms in (10, 20):
            reading = await service.sample(
                status="playing",
                position_ms=position_ms,
                duration_ms=5000,
                volume=60,
                speed=1.0,
                track_path="/tmp/song.mp3",
            )
            assert reading is not None
            assert reading.source == "envelope"
        assert envelope_provider.touch_calls == 1

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
        assert reading.status == "missing"

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


def test_audio_level_service_sanitizes_non_finite_live_levels() -> None:
    async def run() -> None:
        service = AudioLevelService(
            live_provider=_NonFiniteLiveProvider(),
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
        assert reading.left == 0.0
        assert reading.right == 0.0
        assert reading.status == "ready"

    _run(run())


def test_audio_level_service_reports_loading_when_schedule_hook_is_used() -> None:
    async def run() -> None:
        scheduled: list[str] = []

        async def _schedule(track_path: str) -> None:
            scheduled.append(track_path)

        service = AudioLevelService(
            live_provider=_NoLiveProvider(),
            envelope_provider=_MissingEnvelopeProvider(),
            schedule_envelope_analysis=_schedule,
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
        assert reading.source == "fallback"
        assert reading.status == "loading"
        assert scheduled == ["/tmp/song.mp3"]

    _run(run())
