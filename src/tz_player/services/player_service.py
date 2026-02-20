"""Playback orchestration service between UI intent and backend engines.

`PlayerService` is the transport/queue authority. It normalizes backend events,
applies repeat/shuffle rules, emits UI-facing domain events, and combines live or
precomputed audio-level sampling for visualizers.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable
from contextlib import suppress
from dataclasses import dataclass, replace
from typing import Callable, Literal

from tz_player.events import PlayerStateChanged, TrackChanged
from tz_player.services.audio_level_service import (
    AudioLevelService,
    EnvelopeLevelProvider,
)
from tz_player.services.beat_service import BeatReading, BeatService
from tz_player.services.beat_store import BeatParams
from tz_player.services.playback_backend import (
    BackendError,
    BackendEvent,
    MediaChanged,
    PlaybackBackend,
    PositionUpdated,
    StateChanged,
)
from tz_player.services.spectrum_service import SpectrumReading, SpectrumService
from tz_player.services.spectrum_store import SpectrumParams

logger = logging.getLogger(__name__)

STATUS = Literal["idle", "loading", "playing", "paused", "stopped", "error"]
REPEAT = Literal["OFF", "ONE", "ALL"]
SPEED_MIN = 0.5
SPEED_MAX = 4.0
SPEED_STEP = 0.25
STALE_STOP_START_WINDOW_MS = 750
TRACK_END_GRACE_MS = 300


def _format_user_error(
    *, what_failed: str, likely_cause: str, next_step: str, detail: str | None = None
) -> str:
    message = f"{what_failed}\nLikely cause: {likely_cause}\nNext step: {next_step}"
    if detail:
        message = f"{message}\nDetails: {detail}"
    return message


@dataclass(frozen=True)
class TrackInfo:
    """Playback metadata for the currently selected queue item."""

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
    """Serializable snapshot of transport state exposed to the UI."""

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
    level_status: str | None = None
    spectrum_bands: bytes | None = None
    spectrum_source: str | None = None
    spectrum_status: str | None = None
    beat_strength: float | None = None
    beat_is_onset: bool | None = None
    beat_bpm: float | None = None
    beat_source: str | None = None
    beat_status: str | None = None
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
        envelope_provider: EnvelopeLevelProvider | None = None,
        schedule_envelope_analysis: Callable[[str], Awaitable[None]] | None = None,
        spectrum_service: SpectrumService | None = None,
        spectrum_params: SpectrumParams | None = None,
        should_sample_spectrum: Callable[[], bool] | None = None,
        beat_service: BeatService | None = None,
        beat_params: BeatParams | None = None,
        should_sample_beat: Callable[[], bool] | None = None,
        poll_interval_s: float = 0.25,
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
        if default_duration_ms < 1:
            raise ValueError("default_duration_ms must be >= 1")
        self._default_duration_ms = default_duration_ms
        self._state = initial_state or PlayerState()
        self._lock = asyncio.Lock()
        self._stop_requested = False
        self._poll_task: asyncio.Task[None] | None = None
        self._poll_interval = max(0.05, min(1.0, float(poll_interval_s)))
        self._end_handled_item_id: int | None = None
        self._max_position_seen_ms = self._state.position_ms
        self._track_started_monotonic_s: float | None = None
        self._shuffle_order: list[int] = []
        self._shuffle_index: int | None = None
        self._shuffle_playlist_id: int | None = None
        self._audio_level_service = AudioLevelService(
            live_provider=backend,
            envelope_provider=envelope_provider,
            schedule_envelope_analysis=schedule_envelope_analysis,
        )
        self._spectrum_service = spectrum_service
        self._spectrum_params = spectrum_params
        self._should_sample_spectrum = should_sample_spectrum
        self._beat_service = beat_service
        self._beat_params = beat_params
        self._should_sample_beat = should_sample_beat
        self._current_track_path: str | None = None
        self._backend.set_event_handler(self._handle_backend_event)

    @property
    def state(self) -> PlayerState:
        return self._state

    async def start(self) -> None:
        """Start backend and background polling with persisted engine settings."""
        await self._backend.start()
        # Keep backend engine state aligned with persisted/app state before any play action.
        await self._backend.set_volume(self._state.volume)
        await self._backend.set_speed(self._state.speed)
        if self._poll_task is None:
            self._poll_task = asyncio.create_task(self._poll_position())

    async def shutdown(self) -> None:
        """Stop polling loop and perform best-effort backend shutdown."""
        if self._poll_task is not None:
            self._poll_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._poll_task
            self._poll_task = None
        with suppress(Exception):
            await self._backend.shutdown()

    async def play_item(self, playlist_id: int, item_id: int) -> None:
        """Start playback for a specific playlist item and emit state transitions."""
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
                level_status=None,
                spectrum_bands=None,
                spectrum_source=None,
                spectrum_status=None,
                beat_strength=None,
                beat_is_onset=None,
                beat_bpm=None,
                beat_source=None,
                beat_status=None,
                error=None,
            )
            # A stale manual-stop latch must never suppress natural track-end advance.
            self._stop_requested = False
            self._end_handled_item_id = None
            self._max_position_seen_ms = 0
            self._track_started_monotonic_s = None
            shuffle_enabled = self._state.shuffle
        await self._emit_state()
        if shuffle_enabled:
            await self._ensure_shuffle_position(playlist_id, item_id)
        track_info = await self._track_info_provider(playlist_id, item_id)
        track_duration_ms = (
            track_info.duration_ms
            if track_info and track_info.duration_ms is not None
            else None
        )
        duration_ms = (
            track_duration_ms
            if track_duration_ms is not None and track_duration_ms > 0
            else self._default_duration_ms
        )
        if track_info is None:
            self._current_track_path = None
            async with self._lock:
                self._state = replace(
                    self._state,
                    status="error",
                    error=_format_user_error(
                        what_failed="Failed to start playback for selected track.",
                        likely_cause="Track entry is missing, moved, or no longer readable.",
                        next_step="Verify the file path and refresh/remove the playlist entry.",
                    ),
                )
            await self._emit_state()
            return
        self._current_track_path = track_info.path
        try:
            await self._backend.play(
                item_id,
                track_info.path,
                0,
                duration_ms=duration_ms,
            )
        except Exception as exc:
            async with self._lock:
                self._state = replace(
                    self._state,
                    status="error",
                    error=_format_user_error(
                        what_failed="Failed to start playback.",
                        likely_cause="Playback backend could not open or decode the media.",
                        next_step="Verify backend/tooling setup and file accessibility, then retry.",
                        detail=str(exc),
                    ),
                )
            await self._emit_state()
            return
        async with self._lock:
            self._state = replace(
                self._state,
                status="playing",
                duration_ms=duration_ms,
                position_ms=0,
            )
            self._track_started_monotonic_s = time.monotonic()
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
        self._current_track_path = None
        async with self._lock:
            self._stop_requested = True
            self._state = replace(self._state, status="stopped", position_ms=0)
            self._state = replace(
                self._state,
                level_left=None,
                level_right=None,
                level_source=None,
                level_status=None,
                spectrum_bands=None,
                spectrum_source=None,
                spectrum_status=None,
                beat_strength=None,
                beat_is_onset=None,
                beat_bpm=None,
                beat_source=None,
                beat_status=None,
            )
            self._end_handled_item_id = None
            self._max_position_seen_ms = 0
            self._track_started_monotonic_s = None
        await self._backend.stop()
        await self._emit_state()

    async def seek_ratio(self, ratio: float) -> None:
        async with self._lock:
            position = int(self._state.duration_ms * ratio)
            position = _clamp(position, 0, self._state.duration_ms)
            self._state = replace(self._state, position_ms=position)
            self._max_position_seen_ms = max(self._max_position_seen_ms, position)
        await self._backend.seek_ms(position)
        await self._emit_state()

    async def seek_ms(self, position_ms: int) -> None:
        async with self._lock:
            position = _clamp(position_ms, 0, self._state.duration_ms)
            self._state = replace(self._state, position_ms=position)
            self._max_position_seen_ms = max(self._max_position_seen_ms, position)
        await self._backend.seek_ms(position)
        await self._emit_state()

    async def seek_delta_ms(self, delta_ms: int) -> None:
        async with self._lock:
            position = self._state.position_ms + delta_ms
            position = _clamp(position, 0, self._state.duration_ms)
            self._state = replace(self._state, position_ms=position)
            self._max_position_seen_ms = max(self._max_position_seen_ms, position)
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
        """Toggle shuffle mode and build/clear deterministic traversal order."""
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
        """Advance to next track using shuffle/repeat policy when configured."""
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
        """Go to previous track or restart current track when position > 3s."""
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

    async def predict_next_item_id(self) -> int | None:
        """Predict next item without mutating playback position/state."""
        if (
            self._next_track_provider is None
            and self._playlist_item_ids_provider is None
        ):
            return None
        async with self._lock:
            playlist_id = self._state.playlist_id
            item_id = self._state.item_id
            repeat_mode = self._state.repeat_mode
            shuffle = self._state.shuffle
        if playlist_id is None or item_id is None:
            return None
        if repeat_mode == "ONE":
            return item_id
        if shuffle:
            return await self._predict_shuffle_next(
                playlist_id, item_id, wrap=repeat_mode == "ALL"
            )
        if self._next_track_provider is None:
            return None
        return await self._next_track_provider(
            playlist_id, item_id, repeat_mode == "ALL"
        )

    async def _handle_backend_event(self, event: BackendEvent) -> None:
        """Normalize backend events into player state and track-end decisions."""
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
                    self._max_position_seen_ms = max(self._max_position_seen_ms, pos)
                    if abs(pos - last_pos) >= 100:
                        emit = True
            elif isinstance(event, MediaChanged):
                if event.duration_ms != self._state.duration_ms:
                    self._state = replace(self._state, duration_ms=event.duration_ms)
                    emit = True
            elif isinstance(event, StateChanged):
                track_age_s: float | None = None
                if self._track_started_monotonic_s is not None:
                    track_age_s = time.monotonic() - self._track_started_monotonic_s
                if event.status == "loading" and self._state.status in {
                    "playing",
                    "paused",
                }:
                    return
                if (
                    event.status == "stopped"
                    and not self._stop_requested
                    and previous_status == "playing"
                    and self._state.duration_ms > 0
                    and self._max_position_seen_ms <= STALE_STOP_START_WINDOW_MS
                    and (track_age_s is None or track_age_s <= 2.0)
                ):
                    # Guard only clearly stale stops shortly after a new track start.
                    return
                if event.status != self._state.status:
                    self._state = replace(self._state, status=event.status)
                    emit = True
                if (
                    event.status == "stopped"
                    and not self._stop_requested
                    and previous_status == "playing"
                    and self._state.item_id is not None
                    and self._state.item_id != self._end_handled_item_id
                ):
                    self._end_handled_item_id = self._state.item_id
                    handle_end = True
                if event.status == "stopped" and self._stop_requested:
                    self._stop_requested = False
            elif isinstance(event, BackendError):
                self._state = replace(
                    self._state,
                    status="error",
                    error=_format_user_error(
                        what_failed="Playback backend reported an error.",
                        likely_cause="Backend runtime, codec, or media access failure.",
                        next_step="Check backend setup and media path, then retry playback.",
                        detail=event.message,
                    ),
                )
                emit = True
        if emit:
            await self._emit_state()
        if handle_end:
            await self._handle_track_end()

    async def _handle_track_end(self) -> None:
        """Apply repeat/shuffle policy after a natural track completion event."""
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

    async def _predict_shuffle_next(
        self,
        playlist_id: int,
        item_id: int,
        *,
        wrap: bool,
    ) -> int | None:
        if self._playlist_item_ids_provider is None:
            return None
        item_ids = await self._playlist_item_ids_provider(playlist_id)
        if not item_ids:
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
        next_index = self._shuffle_index + 1
        if 0 <= next_index < len(self._shuffle_order):
            return self._shuffle_order[next_index]
        if wrap and self._shuffle_order:
            return self._shuffle_order[0]
        return None

    async def _rebuild_shuffle_order(
        self,
        playlist_id: int,
        anchor_item_id: int | None,
        *,
        item_ids: list[int] | None = None,
    ) -> bool:
        """Rebuild shuffle order anchored to current item for stable navigation."""
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
        """Poll backend transport/levels and infer end-of-track in edge cases.

        Some backends emit stop/idle transitions too early or inconsistently.
        Polling applies grace-window heuristics to avoid false track-end handling
        while still progressing naturally when playback truly finishes.
        """
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
                    backend_state = await self._backend.get_state()
                    reading = await self._audio_level_service.sample(
                        status=status,
                        position_ms=position,
                        duration_ms=duration,
                        volume=self._state.volume,
                        speed=self._state.speed,
                        track_path=self._current_track_path,
                    )
                    spectrum_reading = await self._sample_spectrum_if_enabled(position)
                    beat_reading = await self._sample_beat_if_enabled(position)
                except Exception:  # pragma: no cover - backend safety net
                    continue
                emit = False
                handle_end = False
                async with self._lock:
                    previous_status = self._state.status
                    track_age_ms: int | None = None
                    if self._track_started_monotonic_s is not None:
                        track_age_ms = int(
                            (time.monotonic() - self._track_started_monotonic_s) * 1000
                        )
                    if position >= 0:
                        self._max_position_seen_ms = max(
                            self._max_position_seen_ms, position
                        )
                    if duration >= 0 and duration != self._state.duration_ms:
                        self._state = replace(self._state, duration_ms=duration)
                        emit = True
                    if position >= 0 and abs(position - self._state.position_ms) >= 100:
                        self._state = replace(self._state, position_ms=position)
                        self._max_position_seen_ms = max(
                            self._max_position_seen_ms, position
                        )
                        emit = True
                    if reading is not None:
                        left = _clamp_float(reading.left, 0.0, 1.0)
                        right = _clamp_float(reading.right, 0.0, 1.0)
                        source = reading.source
                        level_status = reading.status
                    else:
                        left = None
                        right = None
                        source = None
                        level_status = None
                    if (
                        left != self._state.level_left
                        or right != self._state.level_right
                        or source != self._state.level_source
                        or level_status != self._state.level_status
                    ):
                        previous_source = self._state.level_source
                        self._state = replace(
                            self._state,
                            level_left=left,
                            level_right=right,
                            level_source=source,
                            level_status=level_status,
                        )
                        if source != previous_source and source is not None:
                            logger.info(
                                "Audio level source changed: %s -> %s (item_id=%s track_path=%s)",
                                previous_source or "none",
                                source,
                                self._state.item_id,
                                self._current_track_path,
                            )
                        emit = True
                    spectrum_bands: bytes | None
                    spectrum_source: str | None
                    spectrum_status: str | None
                    if spectrum_reading is not None:
                        spectrum_bands = spectrum_reading.bands
                        spectrum_source = spectrum_reading.source
                        spectrum_status = spectrum_reading.status
                    else:
                        spectrum_bands = None
                        spectrum_source = None
                        spectrum_status = None
                    if (
                        spectrum_bands != self._state.spectrum_bands
                        or spectrum_source != self._state.spectrum_source
                        or spectrum_status != self._state.spectrum_status
                    ):
                        self._state = replace(
                            self._state,
                            spectrum_bands=spectrum_bands,
                            spectrum_source=spectrum_source,
                            spectrum_status=spectrum_status,
                        )
                        emit = True
                    beat_strength: float | None
                    beat_is_onset: bool | None
                    beat_bpm: float | None
                    beat_source: str | None
                    beat_status: str | None
                    if beat_reading is not None:
                        beat_strength = beat_reading.strength
                        beat_is_onset = beat_reading.is_beat
                        beat_bpm = beat_reading.bpm
                        beat_source = beat_reading.source
                        beat_status = beat_reading.status
                    else:
                        beat_strength = None
                        beat_is_onset = None
                        beat_bpm = None
                        beat_source = None
                        beat_status = None
                    if (
                        beat_strength != self._state.beat_strength
                        or beat_is_onset != self._state.beat_is_onset
                        or beat_bpm != self._state.beat_bpm
                        or beat_source != self._state.beat_source
                        or beat_status != self._state.beat_status
                    ):
                        self._state = replace(
                            self._state,
                            beat_strength=beat_strength,
                            beat_is_onset=beat_is_onset,
                            beat_bpm=beat_bpm,
                            beat_source=beat_source,
                            beat_status=beat_status,
                        )
                        emit = True
                    if (
                        backend_state in {"stopped", "idle"}
                        and not self._stop_requested
                        and previous_status == "playing"
                        and self._state.item_id is not None
                        and self._state.item_id != self._end_handled_item_id
                        and self._state.duration_ms > 0
                    ):
                        near_end_by_age = (
                            track_age_ms is not None
                            and track_age_ms
                            >= max(0, self._state.duration_ms - TRACK_END_GRACE_MS)
                        )
                        near_end_by_pos = self._max_position_seen_ms >= max(
                            STALE_STOP_START_WINDOW_MS,
                            self._state.duration_ms - TRACK_END_GRACE_MS,
                        )
                        if backend_state == "idle":
                            should_handle_end = near_end_by_age
                        else:
                            should_handle_end = near_end_by_age or near_end_by_pos
                    else:
                        should_handle_end = False
                    if should_handle_end:
                        self._end_handled_item_id = self._state.item_id
                        handle_end = True
                    if backend_state in {"stopped", "idle"} and self._stop_requested:
                        self._stop_requested = False
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
                if handle_end:
                    await self._handle_track_end()
                if emit:
                    await self._emit_state()
        except asyncio.CancelledError:
            return

    async def _sample_spectrum_if_enabled(
        self, position_ms: int
    ) -> SpectrumReading | None:
        if self._spectrum_service is None or self._spectrum_params is None:
            return None
        if self._current_track_path is None:
            return None
        if (
            self._should_sample_spectrum is not None
            and not self._should_sample_spectrum()
        ):
            return None
        try:
            return await self._spectrum_service.sample(
                track_path=self._current_track_path,
                position_ms=max(0, position_ms),
                params=self._spectrum_params,
            )
        except Exception:
            return None

    async def _sample_beat_if_enabled(self, position_ms: int) -> BeatReading | None:
        if self._beat_service is None or self._beat_params is None:
            return None
        if self._current_track_path is None:
            return None
        if self._should_sample_beat is not None and not self._should_sample_beat():
            return None
        try:
            return await self._beat_service.sample(
                track_path=self._current_track_path,
                position_ms=max(0, position_ms),
                params=self._beat_params,
            )
        except Exception:
            return None


def _clamp(value: int, min_value: int, max_value: int) -> int:
    return max(min_value, min(value, max_value))


def _clamp_float(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(value, max_value))
