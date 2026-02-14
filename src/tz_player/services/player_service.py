"""Async player service delegating playback to a backend."""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable
from contextlib import suppress
from dataclasses import dataclass, replace
from typing import Callable, Literal

from tz_player.events import PlayerStateChanged, TrackChanged
from tz_player.services.audio_level_service import AudioLevelService
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
SPEED_MIN = 0.5
SPEED_MAX = 4.0
SPEED_STEP = 0.25


@dataclass(frozen=True)
class TrackInfo:
    title: str | None
    artist: str | None
    album: str | None
    year: int | None
    path: str
    duration_ms: int | None
    genre: str | None = None
    bitrate_kbps: int | None = None


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
    level_left: float | None = None
    level_right: float | None = None
    level_source: str | None = None
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
        playlist_item_ids_provider: Callable[[int], Awaitable[list[int]]] | None = None,
        shuffle_random: random.Random | None = None,
        default_duration_ms: int = 180_000,
        initial_state: PlayerState | None = None,
    ) -> None:
        self._emit_event = emit_event
        self._track_info_provider = track_info_provider
        self._backend = backend
        self._next_track_provider = next_track_provider
        self._prev_track_provider = prev_track_provider
        self._playlist_item_ids_provider = playlist_item_ids_provider
        self._shuffle_random = shuffle_random or random.Random()
        self._default_duration_ms = default_duration_ms
        self._state = initial_state or PlayerState()
        self._lock = asyncio.Lock()
        self._stop_requested = False
        self._poll_task: asyncio.Task[None] | None = None
        self._poll_interval = 0.25
        self._end_handled_item_id: int | None = None
        self._shuffle_order: list[int] = []
        self._shuffle_index: int | None = None
        self._shuffle_playlist_id: int | None = None
        self._audio_level_service = AudioLevelService(live_provider=backend)
        self._backend.set_event_handler(self._handle_backend_event)

    @property
    def state(self) -> PlayerState:
        return self._state

    async def start(self) -> None:
        await self._backend.start()
        # Keep backend engine state aligned with persisted/app state before any play action.
        await self._backend.set_volume(self._state.volume)
        await self._backend.set_speed(self._state.speed)
        if self._poll_task is None:
            self._poll_task = asyncio.create_task(self._poll_position())

    async def shutdown(self) -> None:
        if self._poll_task is not None:
            self._poll_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._poll_task
            self._poll_task = None
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
                level_left=None,
                level_right=None,
                level_source=None,
                error=None,
            )
            # A stale manual-stop latch must never suppress natural track-end advance.
            self._stop_requested = False
            self._end_handled_item_id = None
            shuffle_enabled = self._state.shuffle
        await self._emit_state()
        if shuffle_enabled:
            await self._ensure_shuffle_position(playlist_id, item_id)
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
            new_status: STATUS = (
                "paused" if self._state.status == "playing" else "playing"
            )
            self._state = replace(self._state, status=new_status)
        await self._backend.toggle_pause()
        await self._emit_state()

    async def stop(self) -> None:
        async with self._lock:
            self._stop_requested = True
            self._state = replace(self._state, status="stopped", position_ms=0)
            self._state = replace(
                self._state,
                level_left=None,
                level_right=None,
                level_source=None,
            )
            self._end_handled_item_id = None
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
            speed = self._state.speed + delta_steps * SPEED_STEP
            self._state = replace(
                self._state, speed=_clamp_float(speed, SPEED_MIN, SPEED_MAX)
            )
            speed = self._state.speed
        await self._backend.set_speed(speed)
        await self._emit_state()

    async def set_speed(self, speed: float) -> None:
        async with self._lock:
            self._state = replace(
                self._state, speed=_clamp_float(speed, SPEED_MIN, SPEED_MAX)
            )
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

    async def toggle_shuffle(self, *, anchor_item_id: int | None = None) -> None:
        async with self._lock:
            self._state = replace(self._state, shuffle=not self._state.shuffle)
            shuffle_enabled = self._state.shuffle
            playlist_id = self._state.playlist_id
            current_item_id = self._state.item_id
        if shuffle_enabled and playlist_id is not None:
            anchor = current_item_id or anchor_item_id
            await self._rebuild_shuffle_order(playlist_id, anchor)
        else:
            self._clear_shuffle_order()
        await self._emit_state()

    def _clear_shuffle_order(self) -> None:
        self._shuffle_order = []
        self._shuffle_index = None
        self._shuffle_playlist_id = None

    async def next_track(self) -> None:
        if (
            self._next_track_provider is None
            and self._playlist_item_ids_provider is None
        ):
            return
        async with self._lock:
            playlist_id = self._state.playlist_id
            item_id = self._state.item_id
            repeat_mode = self._state.repeat_mode
            shuffle = self._state.shuffle
        if playlist_id is None or item_id is None:
            return
        if shuffle:
            next_id = await self._shuffle_step(
                playlist_id, item_id, direction=1, wrap=repeat_mode == "ALL"
            )
            if next_id is not None:
                await self.play_item(playlist_id, next_id)
                return
        wrap = repeat_mode == "ALL"
        if self._next_track_provider is None:
            return
        next_id = await self._next_track_provider(playlist_id, item_id, wrap)
        if next_id is None:
            await self.stop()
            return
        await self.play_item(playlist_id, next_id)

    async def previous_track(self) -> None:
        if (
            self._prev_track_provider is None
            and self._playlist_item_ids_provider is None
        ):
            return
        async with self._lock:
            playlist_id = self._state.playlist_id
            item_id = self._state.item_id
            repeat_mode = self._state.repeat_mode
            position_ms = self._state.position_ms
            shuffle = self._state.shuffle
            if playlist_id is None or item_id is None:
                return
        if position_ms > 3000:
            await self.seek_ratio(0.0)
            return
        if shuffle:
            prev_id = await self._shuffle_step(
                playlist_id, item_id, direction=-1, wrap=repeat_mode == "ALL"
            )
            if prev_id is None:
                await self.stop()
                return
            await self.play_item(playlist_id, prev_id)
            return
        if self._prev_track_provider is None:
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
                if (
                    event.status == "stopped"
                    and not self._stop_requested
                    and previous_status in {"playing", "paused"}
                    and self._state.duration_ms > 0
                    and self._state.position_ms < max(0, self._state.duration_ms - 500)
                ):
                    # Guard against late/stale backend "stopped" events from a prior track.
                    return
                if event.status != self._state.status:
                    self._state = replace(self._state, status=event.status)
                    emit = True
                if (
                    event.status == "stopped"
                    and not self._stop_requested
                    and previous_status in {"playing", "paused"}
                    and self._state.item_id is not None
                    and self._state.item_id != self._end_handled_item_id
                ):
                    self._end_handled_item_id = self._state.item_id
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
            shuffle = self._state.shuffle
        if playlist_id is None or item_id is None:
            return
        if repeat_mode == "ONE":
            await self.play_item(playlist_id, item_id)
            return
        if shuffle:
            next_id = await self._shuffle_step(
                playlist_id, item_id, direction=1, wrap=repeat_mode == "ALL"
            )
            if next_id is not None:
                await self.play_item(playlist_id, next_id)
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

    async def _ensure_shuffle_position(self, playlist_id: int, item_id: int) -> None:
        if self._playlist_item_ids_provider is None:
            return
        if not self._shuffle_order or self._shuffle_playlist_id != playlist_id:
            await self._rebuild_shuffle_order(playlist_id, item_id)
            return
        if not self._sync_shuffle_index(item_id):
            await self._rebuild_shuffle_order(playlist_id, item_id)

    def _sync_shuffle_index(self, item_id: int) -> bool:
        try:
            index = self._shuffle_order.index(item_id)
        except ValueError:
            return False
        self._shuffle_index = index
        return True

    async def _shuffle_step(
        self,
        playlist_id: int,
        item_id: int,
        *,
        direction: int,
        wrap: bool,
    ) -> int | None:
        if self._playlist_item_ids_provider is None:
            return None
        item_ids = await self._playlist_item_ids_provider(playlist_id)
        if not item_ids:
            self._clear_shuffle_order()
            return None
        item_id_set = set(item_ids)
        if (
            not self._shuffle_order
            or self._shuffle_playlist_id != playlist_id
            or set(self._shuffle_order) != item_id_set
            or item_id not in item_id_set
        ):
            await self._rebuild_shuffle_order(playlist_id, item_id, item_ids=item_ids)
        if not self._shuffle_order:
            return None
        if not self._sync_shuffle_index(item_id):
            await self._rebuild_shuffle_order(playlist_id, item_id, item_ids=item_ids)
            if not self._sync_shuffle_index(item_id):
                return None
        if self._shuffle_index is None:
            return None
        next_index = self._shuffle_index + direction
        if 0 <= next_index < len(self._shuffle_order):
            self._shuffle_index = next_index
            return self._shuffle_order[next_index]
        if wrap and self._shuffle_order:
            self._shuffle_index = 0 if direction > 0 else len(self._shuffle_order) - 1
            return self._shuffle_order[self._shuffle_index]
        return None

    async def _rebuild_shuffle_order(
        self,
        playlist_id: int,
        anchor_item_id: int | None,
        *,
        item_ids: list[int] | None = None,
    ) -> bool:
        if self._playlist_item_ids_provider is None:
            self._clear_shuffle_order()
            return False
        if item_ids is None:
            item_ids = await self._playlist_item_ids_provider(playlist_id)
        if not item_ids:
            self._clear_shuffle_order()
            self._shuffle_playlist_id = playlist_id
            return False
        anchor = anchor_item_id if anchor_item_id in item_ids else item_ids[0]
        remaining = [item_id for item_id in item_ids if item_id != anchor]
        self._shuffle_random.shuffle(remaining)
        order = [anchor] + remaining
        async with self._lock:
            self._shuffle_order = order
            self._shuffle_index = 0
            self._shuffle_playlist_id = playlist_id
        logger.debug("Shuffle order rebuilt with %d items.", len(order))
        return True

    async def _emit_state(self) -> None:
        await self._emit_event(PlayerStateChanged(self._state))

    async def _poll_position(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._poll_interval)
                async with self._lock:
                    status = self._state.status
                if status not in {"playing", "paused"}:
                    continue
                try:
                    position = await self._backend.get_position_ms()
                    duration = await self._backend.get_duration_ms()
                    reading = await self._audio_level_service.sample(
                        status=status,
                        position_ms=position,
                        duration_ms=duration,
                        volume=self._state.volume,
                        speed=self._state.speed,
                        track_path=None,
                    )
                except Exception:  # pragma: no cover - backend safety net
                    continue
                emit = False
                async with self._lock:
                    if duration >= 0 and duration != self._state.duration_ms:
                        self._state = replace(self._state, duration_ms=duration)
                        emit = True
                    if position >= 0 and abs(position - self._state.position_ms) >= 100:
                        self._state = replace(self._state, position_ms=position)
                        emit = True
                    if reading is not None:
                        left = _clamp_float(reading.left, 0.0, 1.0)
                        right = _clamp_float(reading.right, 0.0, 1.0)
                        source = reading.source
                    else:
                        left = None
                        right = None
                        source = None
                    if (
                        left != self._state.level_left
                        or right != self._state.level_right
                        or source != self._state.level_source
                    ):
                        self._state = replace(
                            self._state,
                            level_left=left,
                            level_right=right,
                            level_source=source,
                        )
                        emit = True
                    item_id = self._state.item_id
                if (
                    status == "playing"
                    and duration > 0
                    and position >= duration
                    and item_id is not None
                    and item_id != self._end_handled_item_id
                ):
                    self._end_handled_item_id = item_id
                    await self._handle_track_end()
                if emit:
                    await self._emit_state()
        except asyncio.CancelledError:
            return


def _clamp(value: int, min_value: int, max_value: int) -> int:
    return max(min_value, min(value, max_value))


def _clamp_float(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(value, max_value))
