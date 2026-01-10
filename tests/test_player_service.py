"""Tests for the fake PlayerService backend."""

from __future__ import annotations

import asyncio
from dataclasses import replace

from tz_player.services.fake_backend import FakePlaybackBackend
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
        assert service.state.speed == 8.0
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
