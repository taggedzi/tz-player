"""Minimal UI tests for the Textual app."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.app import App, ComposeResult

import tz_player.paths as paths
from tz_player.app import TzPlayerApp
from tz_player.services.player_service import PlayerState
from tz_player.services.playlist_store import PlaylistRow, PlaylistStore
from tz_player.ui.actions_menu import ActionsMenuButton, ActionsMenuPopup
from tz_player.ui.playlist_pane import PlaylistPane
from tz_player.ui.playlist_viewport import PlaylistViewport
from tz_player.ui.status_pane import StatusPane
from tz_player.ui.transport_controls import TransportControls


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


def test_app_mounts(tmp_path, monkeypatch) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    app = TzPlayerApp(auto_init=False)

    async def run_app() -> None:
        async with app.run_test():
            await asyncio.sleep(0)
            assert app.query_one(PlaylistPane)
            assert app.query_one(TransportControls)
            app.exit()

    _run(run_app())


def test_playlist_pane_empty_db(tmp_path) -> None:
    store = PlaylistStore(tmp_path / "library.sqlite")

    async def run_app() -> None:
        await store.initialize()
        playlist_id = await store.ensure_playlist("Default")
        pane = PlaylistPane()

        class PaneApp(App):
            def compose(self) -> ComposeResult:
                yield pane

        app = PaneApp()
        async with app.run_test():
            await asyncio.sleep(0)
            await pane.configure(store, playlist_id, None)
            assert pane.total_count == 0
            app.exit()

    _run(run_app())


def test_actions_menu_does_not_resize_header() -> None:
    pane = PlaylistPane()

    class PaneApp(App):
        def compose(self) -> ComposeResult:
            yield pane

    app = PaneApp()

    async def run_app() -> None:
        async with app.run_test() as pilot:
            await asyncio.sleep(0)
            button = pane.query_one(ActionsMenuButton)
            assert "Actions" in str(button.render())
            header = pane.query_one("#playlist-top")
            viewport = pane.query_one(PlaylistViewport)
            header_height = header.size.height
            viewport_height = viewport.size.height
            await pane._open_actions_menu()
            await asyncio.sleep(0)
            assert app.query_one(ActionsMenuPopup)
            assert header.size.height == header_height
            assert viewport.size.height == viewport_height
            await pilot.press("escape")
            await asyncio.sleep(0)
            app.exit()

    _run(run_app())


def test_actions_menu_dismisses_on_escape() -> None:
    pane = PlaylistPane()

    class PaneApp(App):
        def compose(self) -> ComposeResult:
            yield pane

    app = PaneApp()

    async def run_app() -> None:
        async with app.run_test() as pilot:
            await asyncio.sleep(0)
            await pane._open_actions_menu()
            assert app.query_one(ActionsMenuPopup)
            await pilot.press("escape")
            await asyncio.sleep(0)
            assert app.query(ActionsMenuPopup).count == 0
            app.exit()

    _run(run_app())


def test_playlist_pane_refresh_with_tracks(tmp_path) -> None:
    store = PlaylistStore(tmp_path / "library.sqlite")

    async def run_app() -> None:
        await store.initialize()
        playlist_id = await store.ensure_playlist("Default")
        files = [tmp_path / "track1.mp3", tmp_path / "track2.mp3"]
        for path in files:
            path.write_bytes(b"")
        await store.add_tracks(playlist_id, files)
        pane = PlaylistPane()

        class PaneApp(App):
            def compose(self) -> ComposeResult:
                yield pane

        app = PaneApp()
        async with app.run_test():
            await asyncio.sleep(0)
            await pane.configure(store, playlist_id, None)
            assert pane.total_count == 2
            assert pane.query_one(PlaylistViewport)
            app.exit()

    _run(run_app())


def test_playlist_cursor_pins_on_scroll(tmp_path) -> None:
    pane = PlaylistPane()

    def make_row(item_id: int) -> PlaylistRow:
        return PlaylistRow(
            item_id=item_id,
            track_id=item_id,
            pos_key=item_id,
            path=tmp_path / f"track_{item_id}.mp3",
            title=f"Track {item_id}",
            artist="Artist",
            album="Album",
            year=None,
            duration_ms=120000,
            meta_valid=True,
            meta_error=None,
        )

    rows_page1 = [make_row(1), make_row(2), make_row(3)]
    rows_page2 = [make_row(2), make_row(3), make_row(4)]

    async def run_app() -> None:
        pane._rows = rows_page1
        pane.limit = 3
        pane.total_count = 5
        pane.window_offset = 0
        pane.cursor_item_id = 3

        async def fake_refresh() -> None:
            pane._rows = rows_page2

        pane._refresh_window = fake_refresh  # type: ignore[assignment]

        class PaneApp(App):
            def compose(self) -> ComposeResult:
                yield pane

        app = PaneApp()
        async with app.run_test():
            await asyncio.sleep(0)
            pane._update_viewport()
            await pane._move_cursor(1)
            assert pane.window_offset == 1
            assert pane.cursor_item_id == 4
            app.exit()

    _run(run_app())


def test_status_pane_updates() -> None:
    pane = StatusPane()

    class PaneApp(App):
        def compose(self) -> ComposeResult:
            yield pane

    app = PaneApp()

    async def run_app() -> None:
        async with app.run_test():
            await asyncio.sleep(0)
            pane.update_state(
                PlayerState(
                    status="playing",
                    position_ms=65_000,
                    duration_ms=180_000,
                    volume=75,
                    speed=1.25,
                    repeat_mode="ALL",
                    shuffle=True,
                )
            )
            assert pane._time_bar.value_text == "01:05/03:00"
            assert pane._volume_bar.value_text == "75"
            assert pane._speed_bar.value_text == "1.25x"
            assert "playing" in str(pane._status_line.render())
            app.exit()

    _run(run_app())
