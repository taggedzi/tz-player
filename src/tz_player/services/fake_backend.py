"""Fake playback backend for deterministic testing."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass

from .playback_backend import (
    BackendEvent,
    BackendStatus,
    MediaChanged,
    PositionUpdated,
    StateChanged,
)


@dataclass
class _PlaybackState:
    status: BackendStatus = "idle"
    position_ms: int = 0
    duration_ms: int = 0
    volume: int = 100
    speed: float = 1.0


class FakePlaybackBackend:
    """In-memory backend that simulates playback progress."""

    def __init__(
        self,
        *,
        tick_interval_ms: int = 250,
        default_duration_ms: int = 180_000,
    ) -> None:
        self._tick_interval_ms = tick_interval_ms
        self._default_duration_ms = default_duration_ms
        self._state = _PlaybackState()
        self._handler: Callable[[BackendEvent], Awaitable[None]] | None = None
        self._lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def set_event_handler(
        self, handler: Callable[[BackendEvent], Awaitable[None]]
    ) -> None:
        self._handler = handler

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._ticker_loop())

    async def shutdown(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def play(
        self,
        item_id: int,
        track_path: str,
        start_ms: int = 0,
        *,
        duration_ms: int | None = None,
    ) -> None:
        async with self._lock:
            self._state.status = "loading"
        await self._emit(StateChanged("loading"))
        resolved_duration = duration_ms or self._default_duration_ms
        async with self._lock:
            self._state.duration_ms = resolved_duration
            self._state.position_ms = _clamp(start_ms, 0, resolved_duration)
            self._state.status = "playing"
        await self._emit(MediaChanged(resolved_duration))
        await self._emit(
            PositionUpdated(self._state.position_ms, self._state.duration_ms)
        )
        await self._emit(StateChanged("playing"))

    async def toggle_pause(self) -> None:
        async with self._lock:
            if self._state.status == "playing":
                self._state.status = "paused"
            elif self._state.status == "paused":
                self._state.status = "playing"
            else:
                return
            status = self._state.status
        await self._emit(StateChanged(status))

    async def stop(self) -> None:
        async with self._lock:
            self._state.status = "stopped"
            self._state.position_ms = 0
        await self._emit(PositionUpdated(0, self._state.duration_ms))
        await self._emit(StateChanged("stopped"))

    async def seek_ms(self, position_ms: int) -> None:
        async with self._lock:
            pos = _clamp(position_ms, 0, self._state.duration_ms)
            self._state.position_ms = pos
            duration = self._state.duration_ms
        await self._emit(PositionUpdated(pos, duration))

    async def set_volume(self, volume: int) -> None:
        async with self._lock:
            self._state.volume = _clamp(volume, 0, 100)

    async def set_speed(self, speed: float) -> None:
        async with self._lock:
            self._state.speed = _clamp_float(speed, 0.5, 4.0)

    async def get_position_ms(self) -> int:
        async with self._lock:
            return self._state.position_ms

    async def get_duration_ms(self) -> int:
        async with self._lock:
            return self._state.duration_ms

    async def get_state(self) -> BackendStatus:
        async with self._lock:
            return self._state.status

    async def _ticker_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                await asyncio.sleep(self._tick_interval_ms / 1000)
                await self._tick()
        except asyncio.CancelledError:
            pass

    async def _tick(self) -> None:
        async with self._lock:
            if self._state.status != "playing":
                return
            increment = int(self._tick_interval_ms * self._state.speed)
            next_pos = self._state.position_ms + increment
            duration = self._state.duration_ms
            if duration <= 0:
                return
            if next_pos >= duration:
                next_pos = duration
                self._state.status = "stopped"
            self._state.position_ms = next_pos
            status = self._state.status
        await self._emit(PositionUpdated(next_pos, duration))
        if status == "stopped":
            await self._emit(StateChanged("stopped"))

    async def _emit(self, event: BackendEvent) -> None:
        if self._handler is None:
            return
        await self._handler(event)


def _clamp(value: int, min_value: int, max_value: int) -> int:
    return max(min_value, min(value, max_value))


def _clamp_float(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(value, max_value))
