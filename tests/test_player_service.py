"""Tests for the fake PlayerService backend."""

from __future__ import annotations

import asyncio
import random
from dataclasses import replace

from tz_player.services.fake_backend import FakePlaybackBackend
from tz_player.services.playback_backend import (
    BackendError,
    MediaChanged,
    PositionUpdated,
)
from tz_player.services.player_service import PlayerService, PlayerState, TrackInfo


def _run(coro):
    return asyncio.run(coro)


async def _track_info_provider(_playlist_id: int, _item_id: int) -> TrackInfo:
    return TrackInfo(
        title="Song",
        artist="Artist",
        album="Album",
        year=2020,
        path="/tmp/song.mp3",
        duration_ms=500,
    )


def _playlist_item_ids_provider(item_ids: list[int]):
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
        assert service.state.error == "boom"

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
            duration_ms=400,
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
