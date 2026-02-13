"""VLC playback backend using python-vlc."""

from __future__ import annotations

import asyncio
import queue
import threading
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from typing import Any, cast

from .playback_backend import (
    BackendError,
    BackendEvent,
    BackendStatus,
    MediaChanged,
    PositionUpdated,
    StateChanged,
)


@dataclass
class _Command:
    name: str
    args: tuple[Any, ...]
    future: asyncio.Future[Any] | None


class VLCPlaybackBackend:
    """Playback backend backed by a dedicated VLC thread."""

    def __init__(self, *, poll_interval_ms: int = 200) -> None:
        self._poll_interval = poll_interval_ms / 1000
        self._handler: Callable[[BackendEvent], Awaitable[None]] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: queue.Queue[_Command] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def set_event_handler(
        self, handler: Callable[[BackendEvent], Awaitable[None]]
    ) -> None:
        self._handler = handler

    async def start(self) -> None:
        if self._thread is not None:
            return
        self._loop = asyncio.get_running_loop()
        ready_future: asyncio.Future[None] = self._loop.create_future()
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._thread_main,
            args=(ready_future,),
            name="VLCBackendThread",
            daemon=True,
        )
        self._thread.start()
        await ready_future

    async def shutdown(self) -> None:
        if self._thread is None:
            return
        self._stop_event.set()
        self._queue.put(_Command("wake", (), None))
        self._thread.join(timeout=2.0)
        self._thread = None

    async def play(
        self,
        item_id: int,
        track_path: str,
        start_ms: int = 0,
        *,
        duration_ms: int | None = None,
    ) -> None:
        await self._submit("play", track_path, start_ms, duration_ms)

    async def toggle_pause(self) -> None:
        await self._submit("toggle_pause")

    async def stop(self) -> None:
        await self._submit("stop")

    async def seek_ms(self, position_ms: int) -> None:
        await self._submit("seek_ms", position_ms)

    async def set_volume(self, volume: int) -> None:
        await self._submit("set_volume", volume)

    async def set_speed(self, speed: float) -> None:
        await self._submit("set_speed", speed)

    async def get_position_ms(self) -> int:
        return int(await self._submit("get_position_ms"))

    async def get_duration_ms(self) -> int:
        return int(await self._submit("get_duration_ms"))

    async def get_state(self) -> BackendStatus:
        return await self._submit("get_state")

    async def _submit(self, name: str, *args: Any) -> Any:
        if self._loop is None:
            raise RuntimeError("VLC backend not started.")
        future: asyncio.Future[Any] = self._loop.create_future()
        self._queue.put(_Command(name, args, future))
        return await future

    def _thread_main(self, ready_future: asyncio.Future[None]) -> None:
        try:
            import vlc

            instance = vlc.Instance()
            player = instance.media_player_new()
        except Exception as exc:  # pragma: no cover - depends on VLC install
            self._notify_future_exception(
                ready_future,
                RuntimeError(
                    "VLC backend unavailable. Ensure VLC/libVLC is installed."
                ),
            )
            self._emit_event(BackendError(str(exc)))
            return

        self._notify_future_result(ready_future, None)
        last_pos = -1
        last_duration = -1
        last_state: BackendStatus = "idle"

        while not self._stop_event.is_set():
            try:
                cmd = self._queue.get(timeout=self._poll_interval)
            except queue.Empty:
                cmd = None

            if cmd is not None and cmd.name != "wake":
                try:
                    result = self._handle_command(cmd, instance, player)
                    self._notify_future_result(cmd.future, result)
                except Exception as exc:  # pragma: no cover - backend safety net
                    self._notify_future_exception(cmd.future, exc)
                    self._emit_event(BackendError(str(exc)))

            state = _map_state(player)
            if state != last_state:
                last_state = state
                self._emit_event(StateChanged(state))

            if state in {"playing", "paused"}:
                pos = max(player.get_time(), 0)
                duration = max(player.get_length(), 0)
                if duration != last_duration:
                    last_duration = duration
                    if duration > 0:
                        self._emit_event(MediaChanged(duration))
                if pos != last_pos:
                    last_pos = pos
                    self._emit_event(PositionUpdated(pos, duration))
                if state == "playing" and duration > 0 and pos >= duration:
                    player.stop()
                    last_state = "stopped"
                    self._emit_event(StateChanged("stopped"))

        player.stop()

    def _handle_command(self, cmd: _Command, instance: Any, player: Any) -> Any:
        name = cmd.name
        if name == "play":
            track_path, start_ms, _duration_ms = cmd.args
            media = instance.media_new_path(track_path)
            player.set_media(media)
            player.play()
            if start_ms:
                player.set_time(int(start_ms))
            return None
        if name == "toggle_pause":
            player.pause()
            return None
        if name == "stop":
            player.stop()
            return None
        if name == "seek_ms":
            (pos,) = cmd.args
            player.set_time(int(pos))
            return None
        if name == "set_volume":
            (vol,) = cmd.args
            player.audio_set_volume(int(vol))
            return None
        if name == "set_speed":
            (speed,) = cmd.args
            player.set_rate(float(speed))
            return None
        if name == "get_position_ms":
            return max(player.get_time(), 0)
        if name == "get_duration_ms":
            return max(player.get_length(), 0)
        if name == "get_state":
            return _map_state(player)
        raise ValueError(f"Unknown command {name}")

    def _emit_event(self, event: BackendEvent) -> None:
        if self._handler is None or self._loop is None:
            return
        coro = self._handler(event)
        asyncio.run_coroutine_threadsafe(
            cast(Coroutine[Any, Any, None], coro), self._loop
        )

    def _notify_future_result(
        self, future: asyncio.Future[Any] | None, value: Any
    ) -> None:
        if future is None or self._loop is None:
            return
        self._loop.call_soon_threadsafe(future.set_result, value)

    def _notify_future_exception(
        self, future: asyncio.Future[Any] | None, exc: Exception
    ) -> None:
        if future is None or self._loop is None:
            return
        self._loop.call_soon_threadsafe(future.set_exception, exc)


def _map_state(player: Any) -> BackendStatus:
    try:
        state = player.get_state()
    except Exception:
        return "error"
    name = getattr(state, "name", "").lower()
    if name == "playing":
        return "playing"
    if name == "paused":
        return "paused"
    if name in {"stopped", "ended"}:
        return "stopped"
    if name == "opening":
        return "loading"
    if name == "error":
        return "error"
    return "idle"
