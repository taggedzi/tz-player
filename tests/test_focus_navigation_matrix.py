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
    def __init__(self, data_dir: Path, config_dir: Path) -> None:
        self.user_data_dir = str(data_dir)
        self.user_config_dir = str(config_dir)


def _run(coro):
    return asyncio.run(coro)


def _setup_dirs(tmp_path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"

    def fake_app_dirs(app_name: str, appauthor: bool | None = None) -> FakeAppDirs:
        return FakeAppDirs(data_dir, config_dir)

    monkeypatch.setattr(paths, "AppDirs", fake_app_dirs)
    paths.get_app_dirs.cache_clear()


class KeyCaptureApp(TzPlayerApp):
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


async def _configure_app(app: KeyCaptureApp, tmp_path: Path) -> PlaylistPane:
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
                ("transport-play", play_button, False),
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
                await asyncio.sleep(0)
                assert app.calls == ["next", "previous", "play_pause", "stop"]
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
            await pilot.type("track")
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
