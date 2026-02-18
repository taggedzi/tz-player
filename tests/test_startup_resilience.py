"""Startup resilience and backend fallback integration tests."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

import tz_player.app as app_module
import tz_player.paths as paths
from tz_player.app import TzPlayerApp, _classify_db_startup_failure
from tz_player.services.fake_backend import FakePlaybackBackend
from tz_player.services.player_service import PlayerState
from tz_player.state_store import load_state
from tz_player.ui.modals.error import ErrorModal
from tz_player.ui.playlist_pane import PlaylistPane
from tz_player.ui.status_pane import StatusPane


class FakeAppDirs:
    """Path-dir stub used to isolate startup persistence paths in tests."""

    def __init__(self, data_dir: Path, config_dir: Path) -> None:
        self.user_data_dir = str(data_dir)
        self.user_config_dir = str(config_dir)


class FailingBackend(FakePlaybackBackend):
    """Backend stub that fails during startup for resilience-path coverage."""

    async def start(self) -> None:
        raise RuntimeError("backend start failed")


def _run(coro):
    """Run async startup scenario from sync test function."""
    return asyncio.run(coro)


def _setup_dirs(tmp_path, monkeypatch) -> None:
    """Patch path resolution to test-local app data/config directories."""
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"

    def fake_app_dirs(app_name: str, appauthor: bool | None = None) -> FakeAppDirs:
        return FakeAppDirs(data_dir, config_dir)

    monkeypatch.setattr(paths, "AppDirs", fake_app_dirs)
    paths.get_app_dirs.cache_clear()


def test_startup_fails_with_actionable_error_when_vlc_fails(
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
        return FailingBackend()

    monkeypatch.setattr(TzPlayerApp, "push_screen", capture_push_screen)
    monkeypatch.setattr(app_module, "_build_backend", fake_build_backend)
    app = TzPlayerApp(auto_init=False, backend_name="vlc")

    async def run_app() -> None:
        async with app.run_test():
            await asyncio.sleep(0)
            await app._initialize_state()
            pane = app.query_one(PlaylistPane)
            status = app.query_one(StatusPane)
            assert app.state.playback_backend == "vlc"
            assert app.player_service is None
            assert status._player_service is None
            assert app.playlist_id is not None
            assert pane.total_count == 0
            assert app.startup_failed is True
            assert build_calls == ["vlc"]
            assert any(
                isinstance(screen, ErrorModal)
                and "Failed to initialize playback backend." in screen._message
                and "install VLC/libVLC" in screen._message
                for screen in pushed_screens
            )
            app.exit()

    _run(run_app())
    persisted_state = load_state(paths.state_path())
    assert persisted_state.playback_backend == "vlc"


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
                and "Failed to initialize app." in screen._message
                and "verify file permissions/paths" in screen._message
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
        if func is app_module.load_state_with_notice:
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
                and "Failed to initialize app." in screen._message
                and "verify file permissions/paths" in screen._message
                for screen in pushed_screens
            )
            app.exit()

    _run(run_app())


def test_startup_surfaces_notice_when_state_file_is_corrupt(
    tmp_path, monkeypatch
) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    pushed_screens: list[object] = []

    async def capture_push_screen(self, screen):
        pushed_screens.append(screen)
        return None

    state_file = paths.state_path()
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text("{invalid-json", encoding="utf-8")

    monkeypatch.setattr(TzPlayerApp, "push_screen", capture_push_screen)
    app = TzPlayerApp(auto_init=False, backend_name="fake")

    async def run_app() -> None:
        async with app.run_test():
            await asyncio.sleep(0)
            await app._initialize_state()
            assert app.player_service is not None
            assert any(
                isinstance(screen, ErrorModal)
                and "State settings were reset to defaults." in screen._message
                and "Likely cause:" in screen._message
                and "Next step:" in screen._message
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
                and "Failed to initialize playlist database." in screen._message
                and "Likely cause:" in screen._message
                and "Next step:" in screen._message
                for screen in pushed_screens
            )
            app.exit()

    _run(run_app())


def test_classify_db_startup_failure_permission_denied_message(tmp_path) -> None:
    db_file = tmp_path / "db.sqlite3"
    exc = RuntimeError("Database startup failed")
    exc.__cause__ = PermissionError("permission denied")
    message = _classify_db_startup_failure(exc, db_file)
    assert message is not None
    assert "Failed to initialize playlist database." in message
    assert "Likely cause: no permission to read/write the database path." in message
    assert "Next step: check folder permissions and run tz-player again." in message


def test_on_unmount_flushes_pending_state_save(tmp_path, monkeypatch) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    saved_states = []

    async def capture_run_blocking(func, /, *args, **kwargs):
        if func is app_module.save_state:
            saved_states.append(args[1])
            return None
        return func(*args, **kwargs)

    monkeypatch.setattr(app_module, "run_blocking", capture_run_blocking)
    app = TzPlayerApp(auto_init=False, backend_name="fake")
    app.player_state = replace(
        PlayerState(),
        playlist_id=7,
        item_id=3,
        volume=42,
        speed=1.25,
        repeat_mode="ALL",
        shuffle=True,
    )

    async def run_test() -> None:
        app._state_save_task = asyncio.create_task(asyncio.sleep(60))
        await app.on_unmount()

    _run(run_test())
    assert app._state_save_task is None
    assert saved_states
    persisted = saved_states[-1]
    assert persisted.playlist_id == 7
    assert persisted.current_item_id == 3
    assert persisted.volume == 42.0
    assert persisted.speed == 1.25
    assert persisted.repeat_mode == "all"
    assert persisted.shuffle is True
