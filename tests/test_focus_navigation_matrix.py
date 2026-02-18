"""Focus/navigation regression matrix tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

import tz_player.paths as paths
from tz_player.app import TzPlayerApp
from tz_player.services.player_service import PlayerState
from tz_player.ui.actions_menu import ActionsMenuPopup
from tz_player.ui.playlist_pane import PlaylistPane
from tz_player.ui.playlist_viewport import PlaylistViewport
from tz_player.ui.text_button import TextButton


class FakeAppDirs:
    """Path-dir stub for isolating app data/config in temp folders."""

    def __init__(self, data_dir: Path, config_dir: Path) -> None:
        self.user_data_dir = str(data_dir)
        self.user_config_dir = str(config_dir)


def _run(coro):
    """Run async scenario from sync pytest test body."""
    return asyncio.run(coro)


def _setup_dirs(tmp_path, monkeypatch) -> None:
    """Patch AppDirs resolution to test-local directories."""
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"

    def fake_app_dirs(app_name: str, appauthor: bool | None = None) -> FakeAppDirs:
        return FakeAppDirs(data_dir, config_dir)

    monkeypatch.setattr(paths, "AppDirs", fake_app_dirs)
    paths.get_app_dirs.cache_clear()


class KeyCaptureApp(TzPlayerApp):
    """App subclass capturing routed key-action calls for matrix assertions."""

    def __init__(self) -> None:
        super().__init__(auto_init=False)
        self.calls: list[str] = []

    async def action_next_track(self) -> None:
        self.calls.append("next")

    async def action_previous_track(self) -> None:
        self.calls.append("previous")

    async def action_play_pause(self) -> None:
        self.calls.append("play_pause")

    async def action_stop(self) -> None:
        self.calls.append("stop")

    async def action_seek_back(self) -> None:
        self.calls.append("seek_back")

    async def action_seek_forward(self) -> None:
        self.calls.append("seek_forward")

    async def action_seek_back_big(self) -> None:
        self.calls.append("seek_back_big")

    async def action_seek_forward_big(self) -> None:
        self.calls.append("seek_forward_big")

    async def action_seek_start(self) -> None:
        self.calls.append("seek_start")

    async def action_seek_end(self) -> None:
        self.calls.append("seek_end")

    async def action_volume_down(self) -> None:
        self.calls.append("volume_down")

    async def action_volume_up(self) -> None:
        self.calls.append("volume_up")

    async def action_volume_down_big(self) -> None:
        self.calls.append("volume_down_big")

    async def action_volume_up_big(self) -> None:
        self.calls.append("volume_up_big")

    async def action_speed_down(self) -> None:
        self.calls.append("speed_down")

    async def action_speed_up(self) -> None:
        self.calls.append("speed_up")

    async def action_speed_reset(self) -> None:
        self.calls.append("speed_reset")

    async def action_repeat_mode(self) -> None:
        self.calls.append("repeat_mode")

    async def action_shuffle(self) -> None:
        self.calls.append("shuffle")


async def _configure_app(app: KeyCaptureApp, tmp_path: Path) -> PlaylistPane:
    """Initialize app with small playlist and ready transport controls."""
    await app.store.initialize()
    playlist_id = await app.store.ensure_playlist("Default")
    files = [tmp_path / "track1.mp3", tmp_path / "track2.mp3", tmp_path / "track3.mp3"]
    for path in files:
        path.write_bytes(b"")
    await app.store.add_tracks(playlist_id, files)
    pane = app.query_one(PlaylistPane)
    await pane.configure(app.store, playlist_id, None)
    await pane.update_transport_controls(PlayerState())
    return pane


def test_key_routing_matrix_across_focus_targets(tmp_path, monkeypatch) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    app = KeyCaptureApp()

    async def run_app() -> None:
        async with app.run_test() as pilot:
            await asyncio.sleep(0)
            pane = await _configure_app(app, tmp_path)
            viewport = pane.query_one(PlaylistViewport)
            play_button = pane.query_one("#transport-play", TextButton)

            targets = [
                ("playlist-pane", pane, True),
                ("playlist-viewport", viewport, True),
                ("transport-play", play_button, True),
            ]
            for _, widget, should_navigate in targets:
                pane.clear_find_and_focus()
                await asyncio.sleep(0)
                widget.focus()
                await asyncio.sleep(0)

                start_cursor = pane.cursor_item_id
                await pilot.press("down")
                await asyncio.sleep(0)
                if should_navigate:
                    assert pane.cursor_item_id != start_cursor
                else:
                    assert pane.cursor_item_id == start_cursor

                await pilot.press("up")
                await asyncio.sleep(0)
                assert pane.cursor_item_id == start_cursor

                app.calls.clear()
                await pilot.press("n")
                await pilot.press("p")
                await pilot.press("space")
                await pilot.press("x")
                await pilot.press("left")
                await pilot.press("right")
                await pilot.press("shift+left")
                await pilot.press("shift+right")
                await pilot.press("home")
                await pilot.press("end")
                await pilot.press("-")
                await pilot.press("+")
                await pilot.press("shift+-")
                await pilot.press("shift+=")
                await pilot.press("[")
                await pilot.press("]")
                await pilot.press("\\")
                await pilot.press("r")
                await pilot.press("s")
                await asyncio.sleep(0)
                assert app.calls == [
                    "next",
                    "previous",
                    "play_pause",
                    "stop",
                    "seek_back",
                    "seek_forward",
                    "seek_back_big",
                    "seek_forward_big",
                    "seek_start",
                    "seek_end",
                    "volume_down",
                    "volume_up",
                    "volume_down_big",
                    "volume_up_big",
                    "speed_down",
                    "speed_up",
                    "speed_reset",
                    "repeat_mode",
                    "shuffle",
                ]
            app.exit()

    _run(run_app())


def test_escape_priority_popup_then_find(tmp_path, monkeypatch) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    app = KeyCaptureApp()

    async def run_app() -> None:
        async with app.run_test() as pilot:
            await asyncio.sleep(0)
            pane = await _configure_app(app, tmp_path)

            await pilot.press("f")
            for key in "track":
                await pilot.press(key)
            await asyncio.sleep(0.3)
            assert pane.search_active is True
            assert pane.is_find_focused() is True

            await pane._open_actions_menu()
            await asyncio.sleep(0)
            assert len(app.query(ActionsMenuPopup)) == 1

            await pilot.press("escape")
            await asyncio.sleep(0)
            assert len(app.query(ActionsMenuPopup)) == 0
            assert pane.search_active is True
            assert pane.has_find_text() is True

            await pilot.press("escape")
            await asyncio.sleep(0)
            assert pane.search_active is False
            assert pane.has_find_text() is False
            assert app.focused is pane
            app.exit()

    _run(run_app())
