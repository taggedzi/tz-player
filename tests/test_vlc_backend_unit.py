"""Unit tests for VLC backend command behavior without VLC."""

from __future__ import annotations

import asyncio
import threading

import pytest

from tz_player.services.playback_backend import StateChanged
from tz_player.services.vlc_backend import VLCPlaybackBackend, _Command


class _DummyInstance:
    def media_new_path(self, path: str) -> str:
        return path


class _DummyPlayer:
    def __init__(self) -> None:
        self.play_called = False
        self.stop_called = False
        self.time_set = None
        self.media = None

    def set_media(self, media: str) -> None:
        self.media = media

    def play(self) -> None:
        self.play_called = True

    def set_time(self, time_ms: int) -> None:
        self.time_set = time_ms

    def stop(self) -> None:
        self.stop_called = True


class _RecordingBackend(VLCPlaybackBackend):
    def __init__(self) -> None:
        super().__init__()
        self.emitted: list[object] = []

    def _emit_event(self, event: object) -> None:
        self.emitted.append(event)


def test_handle_command_play_stop_no_statechanged() -> None:
    backend = _RecordingBackend()
    instance = _DummyInstance()
    player = _DummyPlayer()

    backend._handle_command(
        _Command("play", ("track.mp3", 0, None), None), instance, player
    )
    assert player.play_called is True
    assert not any(isinstance(event, StateChanged) for event in backend.emitted)

    backend.emitted.clear()
    backend._handle_command(_Command("stop", (), None), instance, player)
    assert player.stop_called is True
    assert not any(isinstance(event, StateChanged) for event in backend.emitted)


def test_get_level_sample_returns_none_when_not_supported() -> None:
    backend = VLCPlaybackBackend()
    sample = asyncio.run(backend.get_level_sample())
    assert sample is None


def test_resolve_future_result_ignores_done_future() -> None:
    async def run() -> None:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[int] = loop.create_future()
        future.set_result(1)
        VLCPlaybackBackend._resolve_future_result(future, 2)
        assert future.result() == 1

    asyncio.run(run())


def test_resolve_future_exception_ignores_done_future() -> None:
    async def run() -> None:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[int] = loop.create_future()
        future.set_result(1)
        VLCPlaybackBackend._resolve_future_exception(future, RuntimeError("x"))
        assert future.result() == 1

    asyncio.run(run())


def test_submit_rejects_when_backend_thread_not_running() -> None:
    async def run() -> None:
        backend = VLCPlaybackBackend()
        backend._loop = asyncio.get_running_loop()  # noqa: SLF001
        backend._thread = threading.Thread()  # noqa: SLF001
        with pytest.raises(RuntimeError, match="VLC backend not started"):
            await backend._submit("get_state")  # noqa: SLF001

    asyncio.run(run())


def test_shutdown_raises_when_thread_does_not_stop() -> None:
    class _StuckThread:
        def join(self, timeout: float | None = None) -> None:
            return None

        def is_alive(self) -> bool:
            return True

    async def run() -> None:
        backend = VLCPlaybackBackend()
        backend._thread = _StuckThread()  # type: ignore[assignment]  # noqa: SLF001
        with pytest.raises(RuntimeError, match="did not stop within 2\\.0 seconds"):
            await backend.shutdown()

    asyncio.run(run())
