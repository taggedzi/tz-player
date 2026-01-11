"""Async player service delegating playback to a backend."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable
from contextlib import suppress
from dataclasses import dataclass, replace
from typing import Callable, Literal

from tz_player.events import PlayerStateChanged, TrackChanged
from tz_player.services.playback_backend import (
    BackendError,
    BackendEvent,
    MediaChanged,
    PlaybackBackend,
    PositionUpdated,
    StateChanged,
)

logger = logging.getLogger(__name__)

STATUS = Literal["idle", "loading", "playing", "paused", "stopped", "error"]
REPEAT = Literal["OFF", "ONE", "ALL"]


@dataclass(frozen=True)
class TrackInfo:
    title: str | None
    artist: str | None
    album: str | None
    year: int | None
    path: str
    duration_ms: int | None


@dataclass(frozen=True)
class PlayerState:
    status: STATUS = "idle"
    playlist_id: int | None = None
    item_id: int | None = None
    position_ms: int = 0
    duration_ms: int = 0
    volume: int = 100
    speed: float = 1.0
    repeat_mode: REPEAT = "OFF"
    shuffle: bool = False
    error: str | None = None


class PlayerService:
    """Owns playback state and emits events to subscribers."""

    def __init__(
        self,
        *,
        emit_event: Callable[[object], Awaitable[None]],
        track_info_provider: Callable[[int, int], Awaitable[TrackInfo | None]],
        backend: PlaybackBackend,
        next_track_provider: Callable[[int, int, bool], Awaitable[int | None]]
        | None = None,
        prev_track_provider: Callable[[int, int, bool], Awaitable[int | None]]
        | None = None,
        default_duration_ms: int = 180_000,
        initial_state: PlayerState | None = None,
    ) -> None:
        self._emit_event = emit_event
        self._track_info_provider = track_info_provider
        self._backend = backend
        self._next_track_provider = next_track_provider
        self._prev_track_provider = prev_track_provider
        self._default_duration_ms = default_duration_ms
        self._state = initial_state or PlayerState()
        self._lock = asyncio.Lock()
        self._stop_requested = False
        self._backend.set_event_handler(self._handle_backend_event)

    @property
    def state(self) -> PlayerState:
        return self._state

    async def start(self) -> None:
        await self._backend.start()

    async def shutdown(self) -> None:
        with suppress(Exception):
            await self._backend.shutdown()

    async def play_item(self, playlist_id: int, item_id: int) -> None:
        async with self._lock:
            self._state = replace(
                self._state,
                status="loading",
                playlist_id=playlist_id,
                item_id=item_id,
                position_ms=0,
                duration_ms=0,
                error=None,
            )
        await self._emit_state()
        track_info = await self._track_info_provider(playlist_id, item_id)
        duration_ms = (
            track_info.duration_ms
            if track_info and track_info.duration_ms is not None
            else self._default_duration_ms
        )
        if track_info is None:
            async with self._lock:
                self._state = replace(
                    self._state, status="error", error="Track not found."
                )
            await self._emit_state()
            return
        try:
            await self._backend.play(
                item_id,
                track_info.path,
                0,
                duration_ms=duration_ms,
            )
        except Exception as exc:
            async with self._lock:
                self._state = replace(self._state, status="error", error=str(exc))
            await self._emit_state()
            return
        async with self._lock:
            self._state = replace(
                self._state,
                status="playing",
                duration_ms=duration_ms,
                position_ms=0,
            )
        await self._emit_event(TrackChanged(track_info))
        await self._emit_state()

    async def toggle_pause(self) -> None:
        async with self._lock:
            if self._state.status not in {"playing", "paused"}:
                return
        await self._backend.toggle_pause()
        await self._emit_state()

    async def stop(self) -> None:
        async with self._lock:
            self._stop_requested = True
            self._state = replace(self._state, status="stopped", position_ms=0)
        await self._backend.stop()
        await self._emit_state()

    async def seek_ratio(self, ratio: float) -> None:
        async with self._lock:
            position = int(self._state.duration_ms * ratio)
            position = _clamp(position, 0, self._state.duration_ms)
            self._state = replace(self._state, position_ms=position)
        await self._backend.seek_ms(position)
        await self._emit_state()

    async def seek_ms(self, position_ms: int) -> None:
        async with self._lock:
            position = _clamp(position_ms, 0, self._state.duration_ms)
            self._state = replace(self._state, position_ms=position)
        await self._backend.seek_ms(position)
        await self._emit_state()

    async def seek_delta_ms(self, delta_ms: int) -> None:
        async with self._lock:
            position = self._state.position_ms + delta_ms
            position = _clamp(position, 0, self._state.duration_ms)
            self._state = replace(self._state, position_ms=position)
        await self._backend.seek_ms(position)
        await self._emit_state()

    async def set_volume(self, vol: int) -> None:
        async with self._lock:
            self._state = replace(self._state, volume=_clamp(vol, 0, 100))
            volume = self._state.volume
        await self._backend.set_volume(volume)
        await self._emit_state()

    async def change_speed(self, delta_steps: int) -> None:
        async with self._lock:
            speed = self._state.speed + delta_steps * 0.25
            self._state = replace(self._state, speed=_clamp_float(speed, 0.5, 8.0))
            speed = self._state.speed
        await self._backend.set_speed(speed)
        await self._emit_state()

    async def set_speed(self, speed: float) -> None:
        async with self._lock:
            self._state = replace(self._state, speed=_clamp_float(speed, 0.5, 8.0))
            speed = self._state.speed
        await self._backend.set_speed(speed)
        await self._emit_state()

    async def reset_speed(self) -> None:
        async with self._lock:
            self._state = replace(self._state, speed=1.0)
        await self._backend.set_speed(1.0)
        await self._emit_state()

    async def cycle_repeat_mode(self) -> None:
        async with self._lock:
            mode = self._state.repeat_mode
            next_mode: REPEAT
            if mode == "OFF":
                next_mode = "ONE"
            elif mode == "ONE":
                next_mode = "ALL"
            else:
                next_mode = "OFF"
            self._state = replace(self._state, repeat_mode=next_mode)
        await self._emit_state()

    async def toggle_shuffle(self) -> None:
        async with self._lock:
            self._state = replace(self._state, shuffle=not self._state.shuffle)
        await self._emit_state()

    async def next_track(self) -> None:
        if self._next_track_provider is None:
            return
        async with self._lock:
            playlist_id = self._state.playlist_id
            item_id = self._state.item_id
            repeat_mode = self._state.repeat_mode
        if playlist_id is None or item_id is None:
            return
        wrap = repeat_mode == "ALL"
        next_id = await self._next_track_provider(playlist_id, item_id, wrap)
        if next_id is None:
            await self.stop()
            return
        await self.play_item(playlist_id, next_id)

    async def previous_track(self) -> None:
        if self._prev_track_provider is None:
            return
        async with self._lock:
            playlist_id = self._state.playlist_id
            item_id = self._state.item_id
            repeat_mode = self._state.repeat_mode
            position_ms = self._state.position_ms
        if playlist_id is None or item_id is None:
            return
        if position_ms > 3000:
            await self.seek_ratio(0.0)
            return
        wrap = repeat_mode == "ALL"
        prev_id = await self._prev_track_provider(playlist_id, item_id, wrap)
        if prev_id is None:
            await self.stop()
            return
        await self.play_item(playlist_id, prev_id)

    async def _handle_backend_event(self, event: BackendEvent) -> None:
        emit = False
        handle_end = False
        async with self._lock:
            previous_status = self._state.status
            if isinstance(event, PositionUpdated):
                pos = max(0, event.position_ms)
                duration = max(0, event.duration_ms)
                if duration != self._state.duration_ms:
                    self._state = replace(self._state, duration_ms=duration)
                    emit = True
                if pos != self._state.position_ms:
                    last_pos = self._state.position_ms
                    self._state = replace(self._state, position_ms=pos)
                    if abs(pos - last_pos) >= 100:
                        emit = True
            elif isinstance(event, MediaChanged):
                if event.duration_ms != self._state.duration_ms:
                    self._state = replace(self._state, duration_ms=event.duration_ms)
                    emit = True
            elif isinstance(event, StateChanged):
                if event.status == "loading" and self._state.status in {
                    "playing",
                    "paused",
                }:
                    return
                if event.status != self._state.status:
                    self._state = replace(self._state, status=event.status)
                    emit = True
                if (
                    event.status == "stopped"
                    and not self._stop_requested
                    and previous_status in {"playing", "paused"}
                    and self._state.item_id is not None
                ):
                    handle_end = True
                if event.status == "stopped" and self._stop_requested:
                    self._stop_requested = False
            elif isinstance(event, BackendError):
                self._state = replace(self._state, status="error", error=event.message)
                emit = True
        if emit:
            await self._emit_state()
        if handle_end:
            await self._handle_track_end()

    async def _handle_track_end(self) -> None:
        async with self._lock:
            playlist_id = self._state.playlist_id
            item_id = self._state.item_id
            repeat_mode = self._state.repeat_mode
        if playlist_id is None or item_id is None:
            return
        if repeat_mode == "ONE":
            await self.play_item(playlist_id, item_id)
            return
        if self._next_track_provider is None:
            await self.stop()
            return
        next_id = await self._next_track_provider(
            playlist_id, item_id, repeat_mode == "ALL"
        )
        if next_id is None:
            await self.stop()
            return
        await self.play_item(playlist_id, next_id)

    async def _emit_state(self) -> None:
        await self._emit_event(PlayerStateChanged(self._state))


def _clamp(value: int, min_value: int, max_value: int) -> int:
    return max(min_value, min(value, max_value))


def _clamp_float(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(value, max_value))
