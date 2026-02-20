"""Tests for the fake PlayerService backend."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import replace

from tz_player.services.beat_service import BeatReading
from tz_player.services.beat_store import BeatParams
from tz_player.services.fake_backend import FakePlaybackBackend
from tz_player.services.playback_backend import (
    BackendError,
    LevelSample,
    MediaChanged,
    PositionUpdated,
    StateChanged,
)
from tz_player.services.player_service import PlayerService, PlayerState, TrackInfo
from tz_player.services.spectrum_service import SpectrumReading
from tz_player.services.spectrum_store import SpectrumParams


def _run(coro):
    """Run async service scenario from sync test functions."""
    return asyncio.run(coro)


async def _track_info_provider(_playlist_id: int, _item_id: int) -> TrackInfo:
    """Return deterministic track metadata for generic service tests."""
    return TrackInfo(
        title="Song",
        artist="Artist",
        album="Album",
        year=2020,
        path="/tmp/song.mp3",
        duration_ms=500,
    )


def _playlist_item_ids_provider(item_ids: list[int]):
    """Build async item-id provider returning a stable copy per invocation."""

    async def provider(_playlist_id: int) -> list[int]:
        return list(item_ids)

    return provider


def test_play_progresses_and_pause_freezes() -> None:
    events: list[object] = []

    async def emit_event(event: object) -> None:
        events.append(event)

    async def run() -> None:
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=_track_info_provider,
            backend=FakePlaybackBackend(tick_interval_ms=50),
        )
        await service.start()
        await service.play_item(1, 1)
        await asyncio.sleep(0.12)
        pos = service.state.position_ms
        assert pos > 0
        await service.toggle_pause()
        await asyncio.sleep(0.12)
        assert service.state.position_ms == pos
        await service.shutdown()

    _run(run())


def test_audio_level_source_change_logs_once_per_transition(caplog) -> None:
    class FlapLevelBackend(FakePlaybackBackend):
        def __init__(self) -> None:
            super().__init__(tick_interval_ms=50)
            self._sample_calls = 0

        async def get_level_sample(self) -> LevelSample | None:
            async with self._lock:  # noqa: SLF001
                if self._state.status not in {"playing", "paused"}:  # noqa: SLF001
                    return None
            self._sample_calls += 1
            if self._sample_calls <= 1:
                return LevelSample(left=0.5, right=0.4)
            return None

    async def emit_event(_event: object) -> None:
        return None

    async def track_info(_playlist_id: int, _item_id: int) -> TrackInfo:
        return TrackInfo(
            title="Song",
            artist="Artist",
            album="Album",
            year=2020,
            path="/tmp/song.mp3",
            duration_ms=5000,
        )

    async def run() -> None:
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=track_info,
            backend=FlapLevelBackend(),
        )
        await service.start()
        await service.play_item(1, 1)
        await asyncio.sleep(0.8)
        await service.shutdown()

    with caplog.at_level(logging.INFO, logger="tz_player.services.player_service"):
        _run(run())
    changes = [
        record.message
        for record in caplog.records
        if "Audio level source changed:" in record.message
    ]
    assert len(changes) == 2
    assert "none -> live" in changes[0]
    assert "live -> fallback" in changes[1]


def test_audio_level_source_stable_does_not_log_spam(caplog) -> None:
    async def emit_event(_event: object) -> None:
        return None

    async def run() -> None:
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=_track_info_provider,
            backend=FakePlaybackBackend(tick_interval_ms=50),
        )
        await service.start()
        await service.play_item(1, 1)
        await asyncio.sleep(0.6)
        await service.shutdown()

    with caplog.at_level(logging.INFO, logger="tz_player.services.player_service"):
        _run(run())
    changes = [
        record.message
        for record in caplog.records
        if "Audio level source changed:" in record.message
    ]
    assert len(changes) == 1
    assert "none -> live" in changes[0]


def test_fake_backend_level_sample_contract() -> None:
    async def run() -> None:
        backend = FakePlaybackBackend(tick_interval_ms=50)
        await backend.start()
        assert await backend.get_level_sample() is None
        await backend.play(1, "/tmp/song.mp3", 0, duration_ms=500)
        sample = await backend.get_level_sample()
        assert sample is not None
        assert 0.0 <= sample.left <= 1.0
        assert 0.0 <= sample.right <= 1.0
        await backend.shutdown()

    _run(run())


def test_play_emits_backend_level_samples_into_player_state() -> None:
    async def emit_event(_event: object) -> None:
        return None

    async def run() -> None:
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=_track_info_provider,
            backend=FakePlaybackBackend(tick_interval_ms=50),
        )
        await service.start()
        await service.play_item(1, 1)
        await asyncio.sleep(0.35)
        assert service.state.level_left is not None
        assert service.state.level_right is not None
        assert service.state.level_source == "live"
        assert 0.0 <= service.state.level_left <= 1.0
        assert 0.0 <= service.state.level_right <= 1.0
        await service.stop()
        assert service.state.level_left is None
        assert service.state.level_right is None
        assert service.state.level_source is None
        await service.shutdown()

    _run(run())


def test_player_service_uses_envelope_source_when_live_unavailable() -> None:
    class NoLiveFakeBackend(FakePlaybackBackend):
        async def get_level_sample(self) -> LevelSample | None:
            return None

    class EnvelopeProvider:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        async def get_level_at(
            self, track_path: str, position_ms: int
        ) -> LevelSample | None:
            self.calls.append((track_path, position_ms))
            return LevelSample(left=0.33, right=0.44)

    async def emit_event(_event: object) -> None:
        return None

    async def run() -> None:
        envelope = EnvelopeProvider()
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=_track_info_provider,
            backend=NoLiveFakeBackend(tick_interval_ms=50),
            envelope_provider=envelope,
        )
        await service.start()
        await service.play_item(1, 1)
        await asyncio.sleep(0.35)
        assert service.state.level_source == "envelope"
        assert service.state.level_left == 0.33
        assert service.state.level_right == 0.44
        assert envelope.calls
        assert envelope.calls[-1][0] == "/tmp/song.mp3"
        await service.shutdown()

    _run(run())


def test_player_service_sets_spectrum_state_when_enabled() -> None:
    class NoLiveFakeBackend(FakePlaybackBackend):
        async def get_level_sample(self) -> LevelSample | None:
            return None

    class SpectrumServiceStub:
        def __init__(self) -> None:
            self.calls: list[tuple[str | None, int, SpectrumParams]] = []

        async def sample(
            self,
            *,
            track_path: str | None,
            position_ms: int,
            params: SpectrumParams,
        ) -> SpectrumReading:
            self.calls.append((track_path, position_ms, params))
            return SpectrumReading(
                bands=bytes([1, 2, 3, 4]),
                source="cache",
                status="ready",
            )

    async def emit_event(_event: object) -> None:
        return None

    async def run() -> None:
        spectrum = SpectrumServiceStub()
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=_track_info_provider,
            backend=NoLiveFakeBackend(tick_interval_ms=50),
            spectrum_service=spectrum,  # type: ignore[arg-type]
            spectrum_params=SpectrumParams(band_count=4, hop_ms=40),
            should_sample_spectrum=lambda: True,
        )
        await service.start()
        await service.play_item(1, 1)
        await asyncio.sleep(0.35)
        assert service.state.spectrum_bands == bytes([1, 2, 3, 4])
        assert service.state.spectrum_source == "cache"
        assert service.state.spectrum_status == "ready"
        assert spectrum.calls
        assert spectrum.calls[-1][0] == "/tmp/song.mp3"
        await service.shutdown()

    _run(run())


def test_player_service_skips_spectrum_sampling_when_disabled() -> None:
    class NoLiveFakeBackend(FakePlaybackBackend):
        async def get_level_sample(self) -> LevelSample | None:
            return None

    class SpectrumServiceStub:
        def __init__(self) -> None:
            self.calls = 0

        async def sample(
            self,
            *,
            track_path: str | None,
            position_ms: int,
            params: SpectrumParams,
        ) -> SpectrumReading:
            del track_path, position_ms, params
            self.calls += 1
            return SpectrumReading(
                bands=bytes([1, 2, 3, 4]),
                source="cache",
                status="ready",
            )

    async def emit_event(_event: object) -> None:
        return None

    async def run() -> None:
        spectrum = SpectrumServiceStub()
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=_track_info_provider,
            backend=NoLiveFakeBackend(tick_interval_ms=50),
            spectrum_service=spectrum,  # type: ignore[arg-type]
            spectrum_params=SpectrumParams(band_count=4, hop_ms=40),
            should_sample_spectrum=lambda: False,
        )
        await service.start()
        await service.play_item(1, 1)
        await asyncio.sleep(0.35)
        assert service.state.spectrum_bands is None
        assert service.state.spectrum_source is None
        assert service.state.spectrum_status is None
        assert spectrum.calls == 0
        await service.shutdown()

    _run(run())


def test_player_service_sets_beat_state_when_enabled() -> None:
    class NoLiveFakeBackend(FakePlaybackBackend):
        async def get_level_sample(self) -> LevelSample | None:
            return None

    class BeatServiceStub:
        def __init__(self) -> None:
            self.calls: list[tuple[str | None, int, BeatParams]] = []

        async def sample(
            self,
            *,
            track_path: str | None,
            position_ms: int,
            params: BeatParams,
        ) -> BeatReading:
            self.calls.append((track_path, position_ms, params))
            return BeatReading(
                strength=0.75,
                is_beat=True,
                bpm=128.0,
                source="cache",
                status="ready",
            )

    async def emit_event(_event: object) -> None:
        return None

    async def run() -> None:
        beat = BeatServiceStub()
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=_track_info_provider,
            backend=NoLiveFakeBackend(tick_interval_ms=50),
            beat_service=beat,  # type: ignore[arg-type]
            beat_params=BeatParams(hop_ms=40),
            should_sample_beat=lambda: True,
        )
        await service.start()
        await service.play_item(1, 1)
        await asyncio.sleep(0.35)
        assert service.state.beat_strength == 0.75
        assert service.state.beat_is_onset is True
        assert service.state.beat_bpm == 128.0
        assert service.state.beat_source == "cache"
        assert service.state.beat_status == "ready"
        assert beat.calls
        assert beat.calls[-1][0] == "/tmp/song.mp3"
        await service.shutdown()

    _run(run())


def test_player_service_skips_beat_sampling_when_disabled() -> None:
    class NoLiveFakeBackend(FakePlaybackBackend):
        async def get_level_sample(self) -> LevelSample | None:
            return None

    class BeatServiceStub:
        def __init__(self) -> None:
            self.calls = 0

        async def sample(
            self,
            *,
            track_path: str | None,
            position_ms: int,
            params: BeatParams,
        ) -> BeatReading:
            del track_path, position_ms, params
            self.calls += 1
            return BeatReading(
                strength=0.5,
                is_beat=False,
                bpm=120.0,
                source="cache",
                status="ready",
            )

    async def emit_event(_event: object) -> None:
        return None

    async def run() -> None:
        beat = BeatServiceStub()
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=_track_info_provider,
            backend=NoLiveFakeBackend(tick_interval_ms=50),
            beat_service=beat,  # type: ignore[arg-type]
            beat_params=BeatParams(hop_ms=40),
            should_sample_beat=lambda: False,
        )
        await service.start()
        await service.play_item(1, 1)
        await asyncio.sleep(0.35)
        assert service.state.beat_strength is None
        assert service.state.beat_is_onset is None
        assert service.state.beat_bpm is None
        assert service.state.beat_source is None
        assert service.state.beat_status is None
        assert beat.calls == 0
        await service.shutdown()

    _run(run())


def test_start_applies_initial_volume_and_speed_to_backend() -> None:
    class RecordingBackend:
        def __init__(self) -> None:
            self.handler = None
            self.volume: int | None = None
            self.speed: float | None = None

        def set_event_handler(self, handler) -> None:  # type: ignore[no-untyped-def]
            self.handler = handler

        async def start(self) -> None:
            return None

        async def shutdown(self) -> None:
            return None

        async def play(  # type: ignore[no-untyped-def]
            self, item_id, track_path, start_ms=0, *, duration_ms=None
        ) -> None:
            return None

        async def toggle_pause(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        async def seek_ms(self, position_ms: int) -> None:
            return None

        async def set_volume(self, volume: int) -> None:
            self.volume = volume

        async def set_speed(self, speed: float) -> None:
            self.speed = speed

        async def get_position_ms(self) -> int:
            return 0

        async def get_duration_ms(self) -> int:
            return 0

        async def get_state(self) -> str:
            return "idle"

    async def emit_event(_event: object) -> None:
        return None

    async def run() -> None:
        backend = RecordingBackend()
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=_track_info_provider,
            backend=backend,  # type: ignore[arg-type]
            initial_state=PlayerState(volume=77, speed=1.5),
        )
        await service.start()
        assert backend.volume == 77
        assert backend.speed == 1.5
        await service.shutdown()

    _run(run())


def test_stop_resets_position() -> None:
    async def emit_event(_event: object) -> None:
        return None

    async def run() -> None:
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=_track_info_provider,
            backend=FakePlaybackBackend(tick_interval_ms=50),
        )
        await service.start()
        await service.play_item(1, 1)
        await service.stop()
        assert service.state.status == "stopped"
        assert service.state.position_ms == 0
        await service.shutdown()

    _run(run())


def test_constructor_rejects_non_positive_default_duration() -> None:
    async def emit_event(_event: object) -> None:
        return None

    try:
        PlayerService(
            emit_event=emit_event,
            track_info_provider=_track_info_provider,
            backend=FakePlaybackBackend(tick_interval_ms=50),
            default_duration_ms=0,
        )
    except ValueError as exc:
        assert str(exc) == "default_duration_ms must be >= 1"
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected ValueError for non-positive default_duration_ms")


def test_play_item_non_positive_track_duration_falls_back_to_default() -> None:
    class RecordingBackend:
        def __init__(self) -> None:
            self.handler = None
            self.play_duration_ms: int | None = None

        def set_event_handler(self, handler) -> None:  # type: ignore[no-untyped-def]
            self.handler = handler

        async def start(self) -> None:
            return None

        async def shutdown(self) -> None:
            return None

        async def play(  # type: ignore[no-untyped-def]
            self, item_id, track_path, start_ms=0, *, duration_ms=None
        ) -> None:
            self.play_duration_ms = duration_ms

        async def toggle_pause(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        async def seek_ms(self, position_ms: int) -> None:
            return None

        async def set_volume(self, volume: int) -> None:
            return None

        async def set_speed(self, speed: float) -> None:
            return None

        async def get_position_ms(self) -> int:
            return 0

        async def get_duration_ms(self) -> int:
            return 0

        async def get_state(self) -> str:
            return "idle"

    async def emit_event(_event: object) -> None:
        return None

    async def track_info(_playlist_id: int, _item_id: int) -> TrackInfo:
        return TrackInfo(
            title="Song",
            artist=None,
            album=None,
            year=None,
            path="/tmp/song.mp3",
            duration_ms=0,
        )

    async def run() -> None:
        backend = RecordingBackend()
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=track_info,
            backend=backend,  # type: ignore[arg-type]
            default_duration_ms=1234,
        )
        await service.start()
        await service.play_item(1, 1)
        assert backend.play_duration_ms == 1234
        assert service.state.duration_ms == 1234
        await service.shutdown()

    _run(run())


def test_seek_and_clamps() -> None:
    async def emit_event(_event: object) -> None:
        return None

    async def run() -> None:
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=_track_info_provider,
            backend=FakePlaybackBackend(tick_interval_ms=50),
        )
        await service.start()
        await service.play_item(1, 1)
        await service.seek_ratio(2.0)
        assert service.state.position_ms == service.state.duration_ms
        await service.seek_delta_ms(-10_000)
        assert service.state.position_ms == 0
        await service.shutdown()

    _run(run())


def test_volume_speed_repeat_shuffle() -> None:
    async def emit_event(_event: object) -> None:
        return None

    async def run() -> None:
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=_track_info_provider,
            backend=FakePlaybackBackend(tick_interval_ms=50),
            initial_state=PlayerState(volume=50, speed=1.0),
        )
        await service.start()
        await service.set_volume(200)
        assert service.state.volume == 100
        await service.set_volume(-5)
        assert service.state.volume == 0
        await service.change_speed(40)
        assert service.state.speed == 4.0
        await service.change_speed(-40)
        assert service.state.speed == 0.5
        await service.reset_speed()
        assert service.state.speed == 1.0
        await service.cycle_repeat_mode()
        assert service.state.repeat_mode == "ONE"
        await service.cycle_repeat_mode()
        assert service.state.repeat_mode == "ALL"
        await service.cycle_repeat_mode()
        assert service.state.repeat_mode == "OFF"
        await service.toggle_shuffle()
        assert service.state.shuffle is True
        await service.shutdown()

    _run(run())


def test_backend_event_handling_is_safe() -> None:
    async def emit_event(_event: object) -> None:
        return None

    async def run() -> None:
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=_track_info_provider,
            backend=FakePlaybackBackend(tick_interval_ms=50),
        )
        await service._handle_backend_event(PositionUpdated(1000, 2000))
        assert service.state.position_ms == 1000
        assert service.state.duration_ms == 2000
        await service._handle_backend_event(MediaChanged(3000))
        assert service.state.duration_ms == 3000
        await service._handle_backend_event(BackendError("boom"))
        assert service.state.status == "error"
        assert service.state.error is not None
        assert "Playback backend reported an error." in service.state.error
        assert "Likely cause:" in service.state.error
        assert "Next step:" in service.state.error
        assert "Details: boom" in service.state.error

    _run(run())


def test_play_item_missing_track_sets_actionable_error() -> None:
    async def emit_event(_event: object) -> None:
        return None

    async def missing_track(_playlist_id: int, _item_id: int) -> TrackInfo | None:
        return None

    async def run() -> None:
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=missing_track,
            backend=FakePlaybackBackend(tick_interval_ms=50),
        )
        await service.play_item(1, 1)
        assert service.state.status == "error"
        assert service.state.error is not None
        assert "Failed to start playback for selected track." in service.state.error
        assert "Likely cause:" in service.state.error
        assert "Next step:" in service.state.error

    _run(run())


def test_next_prev_navigation() -> None:
    async def emit_event(_event: object) -> None:
        return None

    async def track_info(_playlist_id: int, item_id: int) -> TrackInfo:
        return TrackInfo(
            title=f"Song {item_id}",
            artist=None,
            album=None,
            year=None,
            path=f"/tmp/{item_id}.mp3",
            duration_ms=5000,
        )

    async def next_provider(_playlist_id: int, item_id: int, wrap: bool) -> int | None:
        if item_id == 1:
            return 2
        if item_id == 2:
            return 3
        return 1 if wrap else None

    async def prev_provider(_playlist_id: int, item_id: int, wrap: bool) -> int | None:
        if item_id == 3:
            return 2
        if item_id == 2:
            return 1
        return 3 if wrap else None

    async def run() -> None:
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=track_info,
            backend=FakePlaybackBackend(tick_interval_ms=50),
            next_track_provider=next_provider,
            prev_track_provider=prev_provider,
            initial_state=PlayerState(playlist_id=1, item_id=2),
        )
        await service.start()
        await service.next_track()
        assert service.state.item_id == 3
        await service.previous_track()
        assert service.state.item_id == 2
        await service.shutdown()

    _run(run())


def test_predict_next_item_id_repeat_and_linear_provider() -> None:
    async def emit_event(_event: object) -> None:
        return None

    async def next_provider(_playlist_id: int, item_id: int, wrap: bool) -> int | None:
        if item_id == 1:
            return 2
        return 1 if wrap else None

    async def run() -> None:
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=_track_info_provider,
            backend=FakePlaybackBackend(tick_interval_ms=50),
            next_track_provider=next_provider,
            initial_state=PlayerState(
                playlist_id=1, item_id=1, repeat_mode="OFF", shuffle=False
            ),
        )
        assert await service.predict_next_item_id() == 2
        service._state = replace(service._state, repeat_mode="ONE")
        assert await service.predict_next_item_id() == 1
        service._state = replace(service._state, repeat_mode="ALL", item_id=5)
        assert await service.predict_next_item_id() == 1

    _run(run())


def test_predict_next_item_id_shuffle_path() -> None:
    async def emit_event(_event: object) -> None:
        return None

    async def track_info(_playlist_id: int, item_id: int) -> TrackInfo:
        return TrackInfo(
            title=f"Song {item_id}",
            artist=None,
            album=None,
            year=None,
            path=f"/tmp/{item_id}.mp3",
            duration_ms=400,
        )

    async def run() -> None:
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=track_info,
            backend=FakePlaybackBackend(tick_interval_ms=50),
            playlist_item_ids_provider=_playlist_item_ids_provider([1, 2, 3]),
            shuffle_random=random.Random(7),
            initial_state=PlayerState(
                playlist_id=1, item_id=1, repeat_mode="ALL", shuffle=True
            ),
        )
        next_id = await service.predict_next_item_id()
        assert next_id in {2, 3}
        assert next_id != 1

    _run(run())


def test_track_end_advance_not_blocked_by_stale_stop_latch() -> None:
    class SilentStopBackend:
        def __init__(self) -> None:
            self.handler = None

        def set_event_handler(self, handler) -> None:  # type: ignore[no-untyped-def]
            self.handler = handler

        async def start(self) -> None:
            return None

        async def shutdown(self) -> None:
            return None

        async def play(  # type: ignore[no-untyped-def]
            self, item_id, track_path, start_ms=0, *, duration_ms=None
        ) -> None:
            return None

        async def toggle_pause(self) -> None:
            return None

        async def stop(self) -> None:
            # Intentionally emits no StateChanged("stopped"), leaving stop latch stale.
            return None

        async def seek_ms(self, position_ms: int) -> None:
            return None

        async def set_volume(self, volume: int) -> None:
            return None

        async def set_speed(self, speed: float) -> None:
            return None

        async def get_position_ms(self) -> int:
            return 0

        async def get_duration_ms(self) -> int:
            return 1000

        async def get_state(self) -> str:
            return "playing"

    async def emit_event(_event: object) -> None:
        return None

    async def track_info(_playlist_id: int, item_id: int) -> TrackInfo:
        return TrackInfo(
            title=f"Song {item_id}",
            artist=None,
            album=None,
            year=None,
            path=f"/tmp/{item_id}.mp3",
            duration_ms=400,
        )

    async def next_provider(_playlist_id: int, item_id: int, _wrap: bool) -> int | None:
        if item_id == 1:
            return 2
        return None

    async def run() -> None:
        backend = SilentStopBackend()
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=track_info,
            backend=backend,  # type: ignore[arg-type]
            next_track_provider=next_provider,
            initial_state=PlayerState(playlist_id=1, item_id=1, status="playing"),
        )
        await service.start()
        await service.stop()  # Leaves stale stop latch in this backend simulation.
        await service.play_item(1, 1)  # Must clear latch.
        # Simulate that playback has progressed before backend emits natural stop.
        await service._handle_backend_event(PositionUpdated(1200, 5000))
        await service._handle_backend_event(StateChanged("stopped"))  # Natural end.
        assert service.state.item_id == 2
        await service.shutdown()

    _run(run())


def test_stale_stopped_event_is_ignored_when_position_near_track_start() -> None:
    async def emit_event(_event: object) -> None:
        return None

    async def run() -> None:
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=_track_info_provider,
            backend=FakePlaybackBackend(tick_interval_ms=50),
        )
        # Simulate active playback shortly after track start.
        service._state = replace(
            service.state,
            status="playing",
            playlist_id=1,
            item_id=2,
            position_ms=100,
            duration_ms=5000,
        )
        await service._handle_backend_event(StateChanged("stopped"))
        # Stale stop should not clobber current playback state.
        assert service.state.status == "playing"
        assert service.state.item_id == 2
        await service.shutdown()

    _run(run())


def test_stopped_event_mid_track_can_advance_when_not_manual_stop() -> None:
    async def emit_event(_event: object) -> None:
        return None

    async def track_info(_playlist_id: int, item_id: int) -> TrackInfo:
        return TrackInfo(
            title=f"Song {item_id}",
            artist=None,
            album=None,
            year=None,
            path=f"/tmp/{item_id}.mp3",
            duration_ms=5000,
        )

    async def next_provider(_playlist_id: int, item_id: int, _wrap: bool) -> int | None:
        return 2 if item_id == 1 else None

    async def run() -> None:
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=track_info,
            backend=FakePlaybackBackend(tick_interval_ms=50),
            next_track_provider=next_provider,
            initial_state=PlayerState(
                status="playing",
                playlist_id=1,
                item_id=1,
                position_ms=1000,
                duration_ms=5000,
                repeat_mode="ALL",
            ),
        )
        await service._handle_backend_event(StateChanged("stopped"))
        assert service.state.item_id == 2
        assert service.state.status == "playing"
        await service.shutdown()

    _run(run())


def test_stopped_event_after_progress_with_reset_position_advances() -> None:
    async def emit_event(_event: object) -> None:
        return None

    async def track_info(_playlist_id: int, item_id: int) -> TrackInfo:
        return TrackInfo(
            title=f"Song {item_id}",
            artist=None,
            album=None,
            year=None,
            path=f"/tmp/{item_id}.mp3",
            duration_ms=5000,
        )

    async def next_provider(_playlist_id: int, item_id: int, _wrap: bool) -> int | None:
        return 2 if item_id == 1 else None

    async def run() -> None:
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=track_info,
            backend=FakePlaybackBackend(tick_interval_ms=50),
            next_track_provider=next_provider,
            initial_state=PlayerState(
                status="playing",
                playlist_id=1,
                item_id=1,
                position_ms=0,
                duration_ms=5000,
                repeat_mode="ALL",
            ),
        )
        # Simulate normal progress, then a backend reset to 0 before stop.
        await service._handle_backend_event(PositionUpdated(1500, 5000))
        await service._handle_backend_event(PositionUpdated(0, 5000))
        await service._handle_backend_event(StateChanged("stopped"))
        assert service.state.item_id == 2
        assert service.state.status == "playing"
        await service.shutdown()

    _run(run())


def test_stopped_event_advances_after_elapsed_play_time_with_low_position() -> None:
    async def emit_event(_event: object) -> None:
        return None

    async def track_info(_playlist_id: int, item_id: int) -> TrackInfo:
        return TrackInfo(
            title=f"Song {item_id}",
            artist=None,
            album=None,
            year=None,
            path=f"/tmp/{item_id}.mp3",
            duration_ms=5000,
        )

    async def next_provider(_playlist_id: int, item_id: int, _wrap: bool) -> int | None:
        return 2 if item_id == 1 else None

    async def run() -> None:
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=track_info,
            backend=FakePlaybackBackend(tick_interval_ms=50),
            next_track_provider=next_provider,
            initial_state=PlayerState(
                status="playing",
                playlist_id=1,
                item_id=1,
                position_ms=0,
                duration_ms=5000,
                repeat_mode="ALL",
            ),
        )
        # Simulate "playing for a while" even if backend position never advanced.
        service._track_started_monotonic_s = time.monotonic() - 10.0
        await service._handle_backend_event(StateChanged("stopped"))
        assert service.state.item_id == 2
        assert service.state.status == "playing"
        await service.shutdown()

    _run(run())


def test_stopped_event_while_paused_does_not_advance() -> None:
    async def emit_event(_event: object) -> None:
        return None

    async def track_info(_playlist_id: int, item_id: int) -> TrackInfo:
        return TrackInfo(
            title=f"Song {item_id}",
            artist=None,
            album=None,
            year=None,
            path=f"/tmp/{item_id}.mp3",
            duration_ms=5000,
        )

    async def next_provider(_playlist_id: int, item_id: int, _wrap: bool) -> int | None:
        return 2 if item_id == 1 else None

    async def run() -> None:
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=track_info,
            backend=FakePlaybackBackend(tick_interval_ms=50),
            next_track_provider=next_provider,
            initial_state=PlayerState(
                status="paused",
                playlist_id=1,
                item_id=1,
                position_ms=1000,
                duration_ms=5000,
                repeat_mode="ALL",
            ),
        )
        await service._handle_backend_event(StateChanged("stopped"))
        assert service.state.item_id == 1
        assert service.state.status == "stopped"
        await service.shutdown()

    _run(run())


def test_poll_fallback_advances_when_backend_stops_without_event() -> None:
    class PollOnlyStopBackend:
        def __init__(self) -> None:
            self._state = "idle"
            self._position_ms = 0
            self._duration_ms = 0

        def set_event_handler(self, _handler) -> None:  # type: ignore[no-untyped-def]
            return None

        async def start(self) -> None:
            return None

        async def shutdown(self) -> None:
            return None

        async def play(  # type: ignore[no-untyped-def]
            self, item_id, track_path, start_ms=0, *, duration_ms=None
        ) -> None:
            self._state = "playing"
            self._position_ms = int(start_ms)
            self._duration_ms = int(duration_ms or 1000)

        async def toggle_pause(self) -> None:
            return None

        async def stop(self) -> None:
            self._state = "stopped"

        async def seek_ms(self, position_ms: int) -> None:
            self._position_ms = int(position_ms)

        async def set_volume(self, volume: int) -> None:
            return None

        async def set_speed(self, speed: float) -> None:
            return None

        async def get_position_ms(self) -> int:
            if self._state == "playing":
                self._position_ms = min(self._duration_ms, self._position_ms + 350)
                if self._position_ms >= self._duration_ms:
                    self._state = "stopped"
            return self._position_ms

        async def get_duration_ms(self) -> int:
            return self._duration_ms

        async def get_state(self) -> str:
            return self._state

    async def emit_event(_event: object) -> None:
        return None

    async def track_info(_playlist_id: int, item_id: int) -> TrackInfo:
        duration = 900 if item_id == 1 else 10_000
        return TrackInfo(
            title=f"Song {item_id}",
            artist=None,
            album=None,
            year=None,
            path=f"/tmp/{item_id}.mp3",
            duration_ms=duration,
        )

    async def next_provider(_playlist_id: int, item_id: int, _wrap: bool) -> int | None:
        return 2 if item_id == 1 else None

    async def run() -> None:
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=track_info,
            backend=PollOnlyStopBackend(),  # type: ignore[arg-type]
            next_track_provider=next_provider,
            initial_state=PlayerState(playlist_id=1, item_id=1, repeat_mode="ALL"),
        )
        await service.start()
        await service.play_item(1, 1)
        await asyncio.sleep(1.2)
        assert service.state.item_id == 2
        assert service.state.status == "playing"
        await service.shutdown()

    _run(run())


def test_poll_fallback_does_not_advance_when_paused_and_backend_idle() -> None:
    class IdleWhilePausedBackend:
        def set_event_handler(self, _handler) -> None:  # type: ignore[no-untyped-def]
            return None

        async def start(self) -> None:
            return None

        async def shutdown(self) -> None:
            return None

        async def play(  # type: ignore[no-untyped-def]
            self, item_id, track_path, start_ms=0, *, duration_ms=None
        ) -> None:
            return None

        async def toggle_pause(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        async def seek_ms(self, position_ms: int) -> None:
            return None

        async def set_volume(self, volume: int) -> None:
            return None

        async def set_speed(self, speed: float) -> None:
            return None

        async def get_position_ms(self) -> int:
            return 500

        async def get_duration_ms(self) -> int:
            return 5000

        async def get_state(self) -> str:
            return "idle"

    async def emit_event(_event: object) -> None:
        return None

    async def track_info(_playlist_id: int, item_id: int) -> TrackInfo:
        return TrackInfo(
            title=f"Song {item_id}",
            artist=None,
            album=None,
            year=None,
            path=f"/tmp/{item_id}.mp3",
            duration_ms=5000,
        )

    async def next_provider(_playlist_id: int, item_id: int, _wrap: bool) -> int | None:
        return 2 if item_id == 1 else None

    async def run() -> None:
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=track_info,
            backend=IdleWhilePausedBackend(),  # type: ignore[arg-type]
            next_track_provider=next_provider,
            initial_state=PlayerState(
                status="paused",
                playlist_id=1,
                item_id=1,
                position_ms=500,
                duration_ms=5000,
                repeat_mode="ALL",
            ),
        )
        service._track_started_monotonic_s = time.monotonic() - 10.0
        await service.start()
        await asyncio.sleep(0.35)
        assert service.state.item_id == 1
        assert service.state.status == "paused"
        await service.shutdown()

    _run(run())


def test_poll_fallback_advances_when_backend_goes_idle_without_event() -> None:
    class PollOnlyIdleBackend:
        def __init__(self) -> None:
            self._state = "idle"
            self._position_ms = 0
            self._duration_ms = 0

        def set_event_handler(self, _handler) -> None:  # type: ignore[no-untyped-def]
            return None

        async def start(self) -> None:
            return None

        async def shutdown(self) -> None:
            return None

        async def play(  # type: ignore[no-untyped-def]
            self, item_id, track_path, start_ms=0, *, duration_ms=None
        ) -> None:
            self._state = "playing"
            self._position_ms = int(start_ms)
            self._duration_ms = int(duration_ms or 1000)

        async def toggle_pause(self) -> None:
            return None

        async def stop(self) -> None:
            self._state = "idle"

        async def seek_ms(self, position_ms: int) -> None:
            self._position_ms = int(position_ms)

        async def set_volume(self, volume: int) -> None:
            return None

        async def set_speed(self, speed: float) -> None:
            return None

        async def get_position_ms(self) -> int:
            if self._state == "playing":
                self._position_ms = min(self._duration_ms, self._position_ms + 350)
                if self._position_ms >= self._duration_ms:
                    self._state = "idle"
            return self._position_ms

        async def get_duration_ms(self) -> int:
            return self._duration_ms

        async def get_state(self) -> str:
            return self._state

    async def emit_event(_event: object) -> None:
        return None

    async def track_info(_playlist_id: int, item_id: int) -> TrackInfo:
        duration = 900 if item_id == 1 else 10_000
        return TrackInfo(
            title=f"Song {item_id}",
            artist=None,
            album=None,
            year=None,
            path=f"/tmp/{item_id}.mp3",
            duration_ms=duration,
        )

    async def next_provider(_playlist_id: int, item_id: int, _wrap: bool) -> int | None:
        return 2 if item_id == 1 else None

    async def run() -> None:
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=track_info,
            backend=PollOnlyIdleBackend(),  # type: ignore[arg-type]
            next_track_provider=next_provider,
            initial_state=PlayerState(playlist_id=1, item_id=1, repeat_mode="ALL"),
        )
        await service.start()
        await service.play_item(1, 1)
        await asyncio.sleep(1.2)
        assert service.state.item_id == 2
        assert service.state.status == "playing"
        await service.shutdown()

    _run(run())


def test_poll_fallback_does_not_advance_on_early_idle() -> None:
    class EarlyIdleBackend:
        def __init__(self) -> None:
            self._state = "idle"
            self._position_ms = 0
            self._duration_ms = 0
            self._reads = 0

        def set_event_handler(self, _handler) -> None:  # type: ignore[no-untyped-def]
            return None

        async def start(self) -> None:
            return None

        async def shutdown(self) -> None:
            return None

        async def play(  # type: ignore[no-untyped-def]
            self, item_id, track_path, start_ms=0, *, duration_ms=None
        ) -> None:
            self._state = "playing"
            self._position_ms = int(start_ms)
            self._duration_ms = int(duration_ms or 1000)
            self._reads = 0

        async def toggle_pause(self) -> None:
            return None

        async def stop(self) -> None:
            self._state = "idle"

        async def seek_ms(self, position_ms: int) -> None:
            self._position_ms = int(position_ms)

        async def set_volume(self, volume: int) -> None:
            return None

        async def set_speed(self, speed: float) -> None:
            return None

        async def get_position_ms(self) -> int:
            self._reads += 1
            if self._state == "playing":
                self._position_ms = min(self._duration_ms, self._position_ms + 260)
                if self._reads >= 3:
                    # Simulate transient early idle with low progress.
                    self._state = "idle"
            return self._position_ms

        async def get_duration_ms(self) -> int:
            return self._duration_ms

        async def get_state(self) -> str:
            return self._state

    async def emit_event(_event: object) -> None:
        return None

    async def track_info(_playlist_id: int, item_id: int) -> TrackInfo:
        duration = 60_000 if item_id == 1 else 1000
        return TrackInfo(
            title=f"Song {item_id}",
            artist=None,
            album=None,
            year=None,
            path=f"/tmp/{item_id}.mp3",
            duration_ms=duration,
        )

    async def next_provider(_playlist_id: int, item_id: int, _wrap: bool) -> int | None:
        return 2 if item_id == 1 else None

    async def run() -> None:
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=track_info,
            backend=EarlyIdleBackend(),  # type: ignore[arg-type]
            next_track_provider=next_provider,
            initial_state=PlayerState(playlist_id=1, item_id=1, repeat_mode="ALL"),
        )
        await service.start()
        await service.play_item(1, 1)
        await asyncio.sleep(1.2)
        assert service.state.item_id == 1
        await service.shutdown()

    _run(run())


def test_poll_fallback_does_not_advance_on_idle_with_stale_high_position() -> None:
    class StaleHighPosIdleBackend:
        def __init__(self) -> None:
            self._state = "idle"
            self._position_ms = 0
            self._duration_ms = 0
            self._reads = 0

        def set_event_handler(self, _handler) -> None:  # type: ignore[no-untyped-def]
            return None

        async def start(self) -> None:
            return None

        async def shutdown(self) -> None:
            return None

        async def play(  # type: ignore[no-untyped-def]
            self, item_id, track_path, start_ms=0, *, duration_ms=None
        ) -> None:
            self._state = "playing"
            self._position_ms = int(start_ms)
            self._duration_ms = int(duration_ms or 1000)
            self._reads = 0

        async def toggle_pause(self) -> None:
            return None

        async def stop(self) -> None:
            self._state = "idle"

        async def seek_ms(self, position_ms: int) -> None:
            self._position_ms = int(position_ms)

        async def set_volume(self, volume: int) -> None:
            return None

        async def set_speed(self, speed: float) -> None:
            return None

        async def get_position_ms(self) -> int:
            self._reads += 1
            if self._state == "playing" and self._reads == 2:
                # Simulate bogus near-end position with premature idle transition.
                self._position_ms = max(0, self._duration_ms - 50)
                self._state = "idle"
            return self._position_ms

        async def get_duration_ms(self) -> int:
            return self._duration_ms

        async def get_state(self) -> str:
            return self._state

    async def emit_event(_event: object) -> None:
        return None

    async def track_info(_playlist_id: int, item_id: int) -> TrackInfo:
        duration = 60_000 if item_id == 1 else 1000
        return TrackInfo(
            title=f"Song {item_id}",
            artist=None,
            album=None,
            year=None,
            path=f"/tmp/{item_id}.mp3",
            duration_ms=duration,
        )

    async def next_provider(_playlist_id: int, item_id: int, _wrap: bool) -> int | None:
        return 2 if item_id == 1 else None

    async def run() -> None:
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=track_info,
            backend=StaleHighPosIdleBackend(),  # type: ignore[arg-type]
            next_track_provider=next_provider,
            initial_state=PlayerState(playlist_id=1, item_id=1, repeat_mode="ALL"),
        )
        await service.start()
        await service.play_item(1, 1)
        await asyncio.sleep(1.2)
        assert service.state.item_id == 1
        await service.shutdown()

    _run(run())


def test_shuffle_builds_stable_order() -> None:
    async def emit_event(_event: object) -> None:
        return None

    async def track_info(_playlist_id: int, item_id: int) -> TrackInfo:
        return TrackInfo(
            title=f"Song {item_id}",
            artist=None,
            album=None,
            year=None,
            path=f"/tmp/{item_id}.mp3",
            duration_ms=400,
        )

    async def run() -> None:
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=track_info,
            backend=FakePlaybackBackend(tick_interval_ms=50),
            playlist_item_ids_provider=_playlist_item_ids_provider([1, 2, 3, 4]),
            shuffle_random=random.Random(0),
            initial_state=PlayerState(playlist_id=1, item_id=1),
        )
        await service.start()
        await service.toggle_shuffle()
        await service.next_track()
        assert service.state.item_id == 2
        await service.next_track()
        assert service.state.item_id == 4
        await service.next_track()
        assert service.state.item_id == 3
        await service.shutdown()

    _run(run())


def test_shuffle_previous_tracks_history() -> None:
    async def emit_event(_event: object) -> None:
        return None

    async def track_info(_playlist_id: int, item_id: int) -> TrackInfo:
        return TrackInfo(
            title=f"Song {item_id}",
            artist=None,
            album=None,
            year=None,
            path=f"/tmp/{item_id}.mp3",
            duration_ms=400,
        )

    async def run() -> None:
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=track_info,
            backend=FakePlaybackBackend(tick_interval_ms=50),
            playlist_item_ids_provider=_playlist_item_ids_provider([1, 2, 3, 4]),
            shuffle_random=random.Random(0),
            initial_state=PlayerState(playlist_id=1, item_id=1),
        )
        await service.start()
        await service.toggle_shuffle()
        await service.next_track()
        await service.next_track()
        assert service.state.item_id == 4
        await service.previous_track()
        assert service.state.item_id == 2
        await service.shutdown()

    _run(run())


def test_repeat_one_does_not_advance_with_shuffle() -> None:
    async def emit_event(_event: object) -> None:
        return None

    async def track_info(_playlist_id: int, item_id: int) -> TrackInfo:
        return TrackInfo(
            title=f"Song {item_id}",
            artist=None,
            album=None,
            year=None,
            path=f"/tmp/{item_id}.mp3",
            duration_ms=400,
        )

    async def run() -> None:
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=track_info,
            backend=FakePlaybackBackend(tick_interval_ms=50),
            playlist_item_ids_provider=_playlist_item_ids_provider([1, 2, 3]),
            shuffle_random=random.Random(0),
            initial_state=PlayerState(
                playlist_id=1, item_id=2, shuffle=True, repeat_mode="ONE"
            ),
        )
        await service.start()
        await service._handle_track_end()
        assert service.state.item_id == 2
        await service.shutdown()

    _run(run())


def test_shuffle_repeat_all_wraps() -> None:
    async def emit_event(_event: object) -> None:
        return None

    async def track_info(_playlist_id: int, item_id: int) -> TrackInfo:
        return TrackInfo(
            title=f"Song {item_id}",
            artist=None,
            album=None,
            year=None,
            path=f"/tmp/{item_id}.mp3",
            duration_ms=400,
        )

    async def run() -> None:
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=track_info,
            backend=FakePlaybackBackend(tick_interval_ms=50),
            playlist_item_ids_provider=_playlist_item_ids_provider([1, 2, 3, 4]),
            shuffle_random=random.Random(0),
            initial_state=PlayerState(playlist_id=1, item_id=1, repeat_mode="ALL"),
        )
        await service.start()
        await service.toggle_shuffle()
        await service.next_track()
        await service.next_track()
        await service.next_track()
        assert service.state.item_id == 3
        await service.next_track()
        assert service.state.item_id == 1
        await service.shutdown()

    _run(run())


def test_shuffle_toggle_keeps_anchor() -> None:
    async def emit_event(_event: object) -> None:
        return None

    async def track_info(_playlist_id: int, item_id: int) -> TrackInfo:
        return TrackInfo(
            title=f"Song {item_id}",
            artist=None,
            album=None,
            year=None,
            path=f"/tmp/{item_id}.mp3",
            duration_ms=400,
        )

    async def run() -> None:
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=track_info,
            backend=FakePlaybackBackend(tick_interval_ms=50),
            playlist_item_ids_provider=_playlist_item_ids_provider([1, 2, 3]),
            shuffle_random=random.Random(0),
            initial_state=PlayerState(playlist_id=1, item_id=2),
        )
        await service.start()
        await service.toggle_shuffle()
        assert service.state.item_id == 2
        await service.shutdown()

    _run(run())


def test_shuffle_handles_duplicate_tracks() -> None:
    async def emit_event(_event: object) -> None:
        return None

    async def track_info(_playlist_id: int, item_id: int) -> TrackInfo:
        return TrackInfo(
            title="Song",
            artist=None,
            album=None,
            year=None,
            path="/tmp/duplicate.mp3",
            duration_ms=400,
        )

    async def run() -> None:
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=track_info,
            backend=FakePlaybackBackend(tick_interval_ms=50),
            playlist_item_ids_provider=_playlist_item_ids_provider([10, 11, 12]),
            shuffle_random=random.Random(0),
            initial_state=PlayerState(playlist_id=1, item_id=10),
        )
        await service.start()
        await service.toggle_shuffle()
        await service.next_track()
        assert service.state.item_id == 11
        await service.shutdown()

    _run(run())


def test_prev_restart_threshold() -> None:
    async def emit_event(_event: object) -> None:
        return None

    async def track_info(_playlist_id: int, item_id: int) -> TrackInfo:
        return TrackInfo(
            title=f"Song {item_id}",
            artist=None,
            album=None,
            year=None,
            path=f"/tmp/{item_id}.mp3",
            duration_ms=400,
        )

    async def prev_provider(_playlist_id: int, item_id: int, wrap: bool) -> int | None:
        return item_id - 1 if item_id > 1 else (3 if wrap else None)

    async def run() -> None:
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=track_info,
            backend=FakePlaybackBackend(tick_interval_ms=50),
            prev_track_provider=prev_provider,
            initial_state=PlayerState(playlist_id=1, item_id=2, position_ms=4000),
        )
        await service.start()
        await service.previous_track()
        assert service.state.item_id == 2
        assert service.state.position_ms == 0
        await service.shutdown()

    _run(run())


def test_wrap_and_stop_at_ends() -> None:
    async def emit_event(_event: object) -> None:
        return None

    async def track_info(_playlist_id: int, item_id: int) -> TrackInfo:
        return TrackInfo(
            title=f"Song {item_id}",
            artist=None,
            album=None,
            year=None,
            path=f"/tmp/{item_id}.mp3",
            duration_ms=400,
        )

    async def next_provider(_playlist_id: int, item_id: int, wrap: bool) -> int | None:
        if item_id < 3:
            return item_id + 1
        return 1 if wrap else None

    async def prev_provider(_playlist_id: int, item_id: int, wrap: bool) -> int | None:
        if item_id > 1:
            return item_id - 1
        return 3 if wrap else None

    async def run() -> None:
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=track_info,
            backend=FakePlaybackBackend(tick_interval_ms=50),
            next_track_provider=next_provider,
            prev_track_provider=prev_provider,
            initial_state=PlayerState(playlist_id=1, item_id=3, repeat_mode="ALL"),
        )
        await service.start()
        await service.next_track()
        assert service.state.item_id == 1
        await service.stop()
        service._state = replace(service.state, item_id=3, repeat_mode="OFF")
        await service.next_track()
        assert service.state.status == "stopped"
        service._state = replace(service.state, item_id=1, repeat_mode="OFF")
        await service.previous_track()
        assert service.state.status == "stopped"
        await service.shutdown()

    _run(run())
