"""Startup resilience and backend fallback integration tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

import tz_player.app as app_module
import tz_player.paths as paths
from tz_player.app import TzPlayerApp
from tz_player.services.fake_backend import FakePlaybackBackend
from tz_player.state_store import load_state
from tz_player.ui.modals.error import ErrorModal
from tz_player.ui.playlist_pane import PlaylistPane
from tz_player.ui.status_pane import StatusPane


class FakeAppDirs:
    def __init__(self, data_dir: Path, config_dir: Path) -> None:
        self.user_data_dir = str(data_dir)
        self.user_config_dir = str(config_dir)


class FailingBackend(FakePlaybackBackend):
    async def start(self) -> None:
        raise RuntimeError("backend start failed")


def _run(coro):
    return asyncio.run(coro)


def _setup_dirs(tmp_path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"

    def fake_app_dirs(app_name: str, appauthor: bool | None = None) -> FakeAppDirs:
        return FakeAppDirs(data_dir, config_dir)

    monkeypatch.setattr(paths, "AppDirs", fake_app_dirs)
    paths.get_app_dirs.cache_clear()


def test_startup_falls_back_to_fake_backend_when_vlc_fails(
    tmp_path, monkeypatch
) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    pushed_screens: list[object] = []
    build_calls: list[str] = []

    async def capture_push_screen(self, screen):
        pushed_screens.append(screen)
        return None

    def fake_build_backend(name: str):
        build_calls.append(name)
        if name == "vlc":
            return FailingBackend()
        return FakePlaybackBackend()

    monkeypatch.setattr(TzPlayerApp, "push_screen", capture_push_screen)
    monkeypatch.setattr(app_module, "_build_backend", fake_build_backend)
    app = TzPlayerApp(auto_init=False, backend_name="vlc")

    async def run_app() -> None:
        async with app.run_test():
            await asyncio.sleep(0)
            await app._initialize_state()
            pane = app.query_one(PlaylistPane)
            status = app.query_one(StatusPane)
            assert app.state.playback_backend == "fake"
            assert app.player_service is not None
            assert status._player_service is app.player_service
            assert app.playlist_id is not None
            assert pane.total_count == 0
            assert build_calls == ["vlc", "fake"]
            assert any(
                isinstance(screen, ErrorModal)
                and screen._message == "VLC backend unavailable; using fake backend."
                for screen in pushed_screens
            )
            app.exit()

    _run(run_app())
    persisted_state = load_state(paths.state_path())
    assert persisted_state.playback_backend == "fake"


def test_startup_shows_generic_init_error_when_backend_start_fails(
    tmp_path, monkeypatch
) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    pushed_screens: list[object] = []

    async def capture_push_screen(self, screen):
        pushed_screens.append(screen)
        return None

    monkeypatch.setattr(TzPlayerApp, "push_screen", capture_push_screen)
    monkeypatch.setattr(app_module, "_build_backend", lambda _: FailingBackend())
    app = TzPlayerApp(auto_init=False, backend_name="fake")

    async def run_app() -> None:
        async with app.run_test():
            await asyncio.sleep(0)
            await app._initialize_state()
            pane = app.query_one(PlaylistPane)
            status = app.query_one(StatusPane)
            assert pane.total_count == 0
            assert status._player_service is None
            assert any(
                isinstance(screen, ErrorModal)
                and screen._message == "Failed to initialize. See log file."
                for screen in pushed_screens
            )
            app.exit()

    _run(run_app())


def test_startup_focuses_playlist_on_nominal_init(tmp_path, monkeypatch) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    app = TzPlayerApp(auto_init=False, backend_name="fake")

    async def run_app() -> None:
        async with app.run_test():
            await asyncio.sleep(0)
            await app._initialize_state()
            pane = app.query_one(PlaylistPane)
            assert app.player_service is not None
            assert app.focused is pane
            app.exit()

    _run(run_app())


def test_startup_shows_generic_error_when_state_load_fails(
    tmp_path, monkeypatch
) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    pushed_screens: list[object] = []

    async def capture_push_screen(self, screen):
        pushed_screens.append(screen)
        return None

    async def failing_run_blocking(func, /, *args, **kwargs):
        if func is app_module.load_state:
            raise OSError("read failed")
        return func(*args, **kwargs)

    monkeypatch.setattr(TzPlayerApp, "push_screen", capture_push_screen)
    monkeypatch.setattr(app_module, "run_blocking", failing_run_blocking)
    app = TzPlayerApp(auto_init=False, backend_name="fake")

    async def run_app() -> None:
        async with app.run_test():
            await asyncio.sleep(0)
            await app._initialize_state()
            status = app.query_one(StatusPane)
            assert status._player_service is None
            assert any(
                isinstance(screen, ErrorModal)
                and screen._message == "Failed to initialize. See log file."
                for screen in pushed_screens
            )
            app.exit()

    _run(run_app())


def test_startup_shows_generic_error_when_db_init_fails(tmp_path, monkeypatch) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    pushed_screens: list[object] = []

    async def capture_push_screen(self, screen):
        pushed_screens.append(screen)
        return None

    async def failing_initialize():
        raise RuntimeError("db init failed")

    monkeypatch.setattr(TzPlayerApp, "push_screen", capture_push_screen)
    app = TzPlayerApp(auto_init=False, backend_name="fake")
    monkeypatch.setattr(app.store, "initialize", failing_initialize)

    async def run_app() -> None:
        async with app.run_test():
            await asyncio.sleep(0)
            await app._initialize_state()
            status = app.query_one(StatusPane)
            assert status._player_service is None
            assert any(
                isinstance(screen, ErrorModal)
                and screen._message == "Failed to initialize. See log file."
                for screen in pushed_screens
            )
            app.exit()

    _run(run_app())
