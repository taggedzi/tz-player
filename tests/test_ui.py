"""Minimal UI tests for the Textual app."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.app import App, ComposeResult

import tz_player.paths as paths
from tz_player.app import TzPlayerApp
from tz_player.services.player_service import PlayerState
from tz_player.services.playlist_store import PlaylistRow, PlaylistStore
from tz_player.ui.actions_menu import (
    ActionsMenuButton,
    ActionsMenuPopup,
    ActionsMenuSelected,
)
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
            assert len(app.query(ActionsMenuPopup)) == 0
            app.exit()

    _run(run_app())


def test_actions_menu_keyboard_open_and_select(tmp_path, monkeypatch) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    app = TzPlayerApp(auto_init=False)

    async def run_app() -> None:
        await app.store.initialize()
        playlist_id = await app.store.ensure_playlist("Default")

        async with app.run_test() as pilot:
            await asyncio.sleep(0)
            pane = app.query_one(PlaylistPane)
            selected_actions: list[str] = []

            async def record_action(action: str) -> None:
                selected_actions.append(action)

            pane._handle_actions_menu = record_action  # type: ignore[assignment]
            await pane.configure(app.store, playlist_id, None)
            pane.focus()

            await pilot.press("a")
            await asyncio.sleep(0)
            assert app.query_one(ActionsMenuPopup)

            await pilot.press("down")
            await pilot.press("enter")
            await asyncio.sleep(0)

            assert selected_actions == ["add_folder"]
            assert len(app.query(ActionsMenuPopup)) == 0
            assert app.focused is pane
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


def test_find_filters_playlist_and_escape_resets(tmp_path) -> None:
    store = PlaylistStore(tmp_path / "library.sqlite")

    async def run_app() -> None:
        await store.initialize()
        playlist_id = await store.ensure_playlist("Default")
        files = [
            tmp_path / "moon_song.mp3",
            tmp_path / "sun_song.mp3",
            tmp_path / "moonlight.flac",
        ]
        for path in files:
            path.write_bytes(b"")
        await store.add_tracks(playlist_id, files)
        pane = PlaylistPane()

        class PaneApp(App):
            def compose(self) -> ComposeResult:
                yield pane

        app = PaneApp()
        async with app.run_test() as pilot:
            await asyncio.sleep(0)
            await pane.configure(store, playlist_id, None)
            assert pane.total_count == 3

            pane.focus_find()
            for key in "moon":
                await pilot.press(key)
            await asyncio.sleep(0.3)

            assert pane.search_active is True
            assert pane.total_count == 2
            assert len(pane._rows) == 2
            assert all("moon" in row.path.name.lower() for row in pane._rows)

            await pilot.press("escape")
            await asyncio.sleep(0.1)
            assert pane.search_active is False
            assert pane.total_count == 3
            app.exit()

    _run(run_app())


def test_escape_exits_find_and_restores_global_keys(tmp_path, monkeypatch) -> None:
    _setup_dirs(tmp_path, monkeypatch)

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

    app = KeyCaptureApp()

    async def run_app() -> None:
        async with app.run_test() as pilot:
            await asyncio.sleep(0)
            pane = app.query_one(PlaylistPane)
            await pilot.press("f")
            await asyncio.sleep(0)
            assert app.focused is pane._find_input

            # While find has focus, text input consumes these keys.
            await pilot.press("n")
            await pilot.press("p")
            await pilot.press("space")
            await asyncio.sleep(0)
            assert app.calls == []

            # Escape should exit find mode and return focus to playlist pane.
            await pilot.press("escape")
            await asyncio.sleep(0)
            assert app.focused is pane
            assert pane._find_input.value == ""

            await pilot.press("n")
            await pilot.press("p")
            await pilot.press("space")
            await asyncio.sleep(0)
            assert app.calls == ["next", "previous", "play_pause"]
            app.exit()

    _run(run_app())


def test_clear_playlist_action_resets_state(tmp_path, monkeypatch) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    app = TzPlayerApp(auto_init=False)

    async def run_app() -> None:
        await app.store.initialize()
        playlist_id = await app.store.ensure_playlist("Default")
        track = tmp_path / "track.mp3"
        track.write_bytes(b"")
        await app.store.add_tracks(playlist_id, [track, track])
        async with app.run_test():
            await asyncio.sleep(0)
            pane = app.query_one(PlaylistPane)
            await pane.configure(app.store, playlist_id, None)
            await pane.update_transport_controls(PlayerState())
            assert pane.total_count == 2
            pane.selected_item_ids.add(pane._rows[0].item_id)

            async def confirm(_message: str) -> bool:
                return True

            pane._confirm = confirm  # type: ignore[assignment]
            tasks = []

            def run_worker(coro, exclusive=False):  # type: ignore[no-untyped-def]
                task = asyncio.create_task(coro)
                tasks.append(task)
                return task

            pane.run_worker = run_worker  # type: ignore[assignment]
            await app.on_actions_menu_selected(ActionsMenuSelected("clear_playlist"))
            if tasks:
                await asyncio.gather(*tasks)
            assert pane.total_count == 0
            assert pane._rows == []
            assert pane.cursor_item_id is None
            assert pane.selected_item_ids == set()
            assert pane.playing_item_id is None
            counter_text = str(pane._transport_controls._track_counter.render())
            assert "0000/0000" in counter_text
            assert await app.store.count(playlist_id) == 0
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


def test_playlist_cursor_move_noop_on_empty_rows() -> None:
    pane = PlaylistPane()

    class PaneApp(App):
        def compose(self) -> ComposeResult:
            yield pane

    app = PaneApp()

    async def run_app() -> None:
        async with app.run_test():
            await asyncio.sleep(0)
            pane._rows = []
            pane.total_count = 0
            pane.limit = 3
            pane.window_offset = 0
            pane.cursor_item_id = None
            await pane._move_cursor(1)
            await pane._move_cursor(-1)
            assert pane.cursor_item_id is None
            assert pane.window_offset == 0
            app.exit()

    _run(run_app())


def test_playlist_cursor_clamps_at_top_boundary(tmp_path) -> None:
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

    rows = [make_row(1), make_row(2), make_row(3)]

    async def run_app() -> None:
        refresh_calls = 0

        async def fake_refresh() -> None:
            nonlocal refresh_calls
            refresh_calls += 1

        pane._refresh_window = fake_refresh  # type: ignore[assignment]

        class PaneApp(App):
            def compose(self) -> ComposeResult:
                yield pane

        app = PaneApp()
        async with app.run_test():
            await asyncio.sleep(0)
            pane._rows = rows
            pane.limit = 3
            pane.total_count = 5
            pane.window_offset = 0
            pane.cursor_item_id = 1
            pane._update_viewport()
            await pane._move_cursor(-1)
            assert pane.window_offset == 0
            assert pane.cursor_item_id == 1
            assert refresh_calls == 0
            app.exit()

    _run(run_app())


def test_playlist_cursor_clamps_at_bottom_boundary(tmp_path) -> None:
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

    rows = [make_row(3), make_row(4), make_row(5)]

    async def run_app() -> None:
        refresh_calls = 0

        async def fake_refresh() -> None:
            nonlocal refresh_calls
            refresh_calls += 1

        pane._refresh_window = fake_refresh  # type: ignore[assignment]

        class PaneApp(App):
            def compose(self) -> ComposeResult:
                yield pane

        app = PaneApp()
        async with app.run_test():
            await asyncio.sleep(0)
            pane._rows = rows
            pane.limit = 3
            pane.total_count = 5
            pane.window_offset = 2
            pane.cursor_item_id = 5
            pane._update_viewport()
            await pane._move_cursor(1)
            assert pane.window_offset == 2
            assert pane.cursor_item_id == 5
            assert refresh_calls == 0
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
