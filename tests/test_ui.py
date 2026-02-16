"""Minimal UI tests for the Textual app."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.app import App, ComposeResult
from textual.geometry import Region
from textual.widgets import Input

import tz_player.paths as paths
from tz_player.app import TzPlayerApp
from tz_player.services.player_service import PlayerState
from tz_player.services.playlist_store import PlaylistRow, PlaylistStore
from tz_player.ui.actions_menu import (
    ActionsMenuButton,
    ActionsMenuPopup,
    ActionsMenuSelected,
)
from tz_player.ui.modals.confirm import ConfirmModal
from tz_player.ui.modals.error import ErrorModal
from tz_player.ui.modals.path_input import PathInputModal
from tz_player.ui.playlist_pane import PlaylistPane
from tz_player.ui.playlist_viewport import PlaylistViewport
from tz_player.ui.slider_bar import SliderBar
from tz_player.ui.status_pane import StatusPane
from tz_player.ui.text_button import TextButton
from tz_player.ui.transport_controls import TransportControls


class FakeAppDirs:
    def __init__(self, data_dir: Path, config_dir: Path) -> None:
        self.user_data_dir = str(data_dir)
        self.user_config_dir = str(config_dir)


class _FakeScreenMouseEvent:
    def __init__(self, *, screen_x: int, screen_y: int) -> None:
        self.screen_x = screen_x
        self.screen_y = screen_y
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


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
            assert app.theme == "cyberpunk-clean"
            assert app.query_one(PlaylistPane)
            assert app.query_one(TransportControls)
            app.exit()

    _run(run_app())


def test_focus_style_hooks_exist_for_interactive_widgets() -> None:
    app_css = TzPlayerApp.CSS
    assert "*:focus" in app_css
    assert "#playlist-pane:focus-within" in app_css
    assert "#playlist-find:focus" in app_css
    assert "#playlist-viewport:focus" in app_css
    assert "Input:focus" in app_css
    assert "Button:focus" in app_css
    assert ".text-button:focus" in TextButton.DEFAULT_CSS
    assert "SliderBar:focus" in SliderBar.DEFAULT_CSS
    assert "#actions-menu:focus" in ActionsMenuPopup.DEFAULT_CSS
    assert ".option-list--option-highlighted" in ActionsMenuPopup.DEFAULT_CSS


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


def test_actions_menu_dismiss_is_idempotent_when_detached() -> None:
    popup = ActionsMenuPopup(Region(0, 0, 10, 2))
    popup.dismiss()
    popup.dismiss()


def test_actions_menu_dismisses_on_outside_mouse_down(tmp_path, monkeypatch) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    app = TzPlayerApp(auto_init=False)

    async def run_app() -> None:
        async with app.run_test():
            await asyncio.sleep(0)
            pane = app.query_one(PlaylistPane)
            pane.focus()
            await asyncio.sleep(0)
            await pane._open_actions_menu()
            await asyncio.sleep(0)
            popup = app.query_one(ActionsMenuPopup)
            popup.contains_point = lambda _x, _y: False  # type: ignore[assignment]
            event = _FakeScreenMouseEvent(screen_x=0, screen_y=0)
            app.on_mouse_down(event)
            for _ in range(20):
                if len(app.query(ActionsMenuPopup)) == 0:
                    break
                await asyncio.sleep(0.01)
            assert len(app.query(ActionsMenuPopup)) == 0
            assert event.stopped is True
            for _ in range(20):
                if app.focused is pane:
                    break
                await asyncio.sleep(0.01)
            assert app.focused is pane
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


def test_confirm_modal_escape_dismisses_false() -> None:
    class ConfirmApp(App):
        result: bool | None = None

        def _set_result(self, result: bool) -> None:
            self.result = result

        async def on_mount(self) -> None:
            self.push_screen(ConfirmModal("Proceed?"), callback=self._set_result)

    app = ConfirmApp()

    async def run_app() -> None:
        async with app.run_test() as pilot:
            await asyncio.sleep(0)
            await pilot.press("escape")
            for _ in range(20):
                if app.result is not None:
                    break
                await asyncio.sleep(0.01)
            app.exit()
        assert app.result is False

    _run(run_app())


def test_confirm_modal_enter_dismisses_true() -> None:
    class ConfirmApp(App):
        result: bool | None = None

        def _set_result(self, result: bool) -> None:
            self.result = result

        async def on_mount(self) -> None:
            self.push_screen(ConfirmModal("Proceed?"), callback=self._set_result)

    app = ConfirmApp()

    async def run_app() -> None:
        async with app.run_test() as pilot:
            await asyncio.sleep(0)
            await pilot.press("enter")
            for _ in range(20):
                if app.result is not None:
                    break
                await asyncio.sleep(0.01)
            app.exit()
        assert app.result is True

    _run(run_app())


def test_error_modal_escape_dismisses() -> None:
    class ErrorApp(App):
        dismissed = False

        def _on_result(self, _result: None) -> None:
            self.dismissed = True

        async def on_mount(self) -> None:
            self.push_screen(ErrorModal("Oops"), callback=self._on_result)

    app = ErrorApp()

    async def run_app() -> None:
        async with app.run_test() as pilot:
            await asyncio.sleep(0)
            await pilot.press("escape")
            for _ in range(20):
                if app.dismissed:
                    break
                await asyncio.sleep(0.01)
            app.exit()
        assert app.dismissed is True

    _run(run_app())


def test_error_modal_enter_dismisses() -> None:
    class ErrorApp(App):
        dismissed = False

        def _on_result(self, _result: None) -> None:
            self.dismissed = True

        async def on_mount(self) -> None:
            self.push_screen(ErrorModal("Oops"), callback=self._on_result)

    app = ErrorApp()

    async def run_app() -> None:
        async with app.run_test() as pilot:
            await asyncio.sleep(0)
            await pilot.press("enter")
            for _ in range(20):
                if app.dismissed:
                    break
                await asyncio.sleep(0.01)
            app.exit()
        assert app.dismissed is True

    _run(run_app())


def test_path_input_modal_escape_dismisses_none() -> None:
    class PathInputApp(App):
        result: str | None = "unset"

        def _on_result(self, result: str | None) -> None:
            self.result = result

        async def on_mount(self) -> None:
            self.push_screen(
                PathInputModal("Add files", placeholder="C:\\music\\a.mp3"),
                callback=self._on_result,
            )

    app = PathInputApp()

    async def run_app() -> None:
        async with app.run_test() as pilot:
            await asyncio.sleep(0)
            await pilot.press("escape")
            for _ in range(20):
                if app.result != "unset":
                    break
                await asyncio.sleep(0.01)
            app.exit()
        assert app.result is None

    _run(run_app())


def test_path_input_modal_enter_submits_trimmed_value() -> None:
    class PathInputApp(App):
        result: str | None = None

        def _on_result(self, result: str | None) -> None:
            self.result = result

        async def on_mount(self) -> None:
            self.push_screen(PathInputModal("Add files"), callback=self._on_result)

    app = PathInputApp()

    async def run_app() -> None:
        async with app.run_test() as pilot:
            await asyncio.sleep(0)
            field = app.screen.query_one("#path-input", Input)
            field.value = "  a.mp3  "
            await pilot.press("enter")
            for _ in range(20):
                if app.result is not None:
                    break
                await asyncio.sleep(0.01)
            app.exit()
        assert app.result == "a.mp3"

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


def test_find_enter_returns_focus_and_keeps_filter(tmp_path) -> None:
    store = PlaylistStore(tmp_path / "library.sqlite")

    async def run_app() -> None:
        await store.initialize()
        playlist_id = await store.ensure_playlist("Default")
        files = [
            tmp_path / "moon_song.mp3",
            tmp_path / "sun_song.mp3",
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
            pane.focus_find()
            for key in "moon":
                await pilot.press(key)
            await asyncio.sleep(0.3)

            assert pane.search_active is True
            assert pane.total_count == 1
            assert pane.is_find_focused() is True

            await pilot.press("enter")
            await asyncio.sleep(0)
            assert app.focused is pane
            assert pane.search_active is True
            assert pane.total_count == 1
            assert pane.has_find_text() is True
            app.exit()

    _run(run_app())


def test_escape_clears_find_when_query_exists_but_focus_moved(
    tmp_path, monkeypatch
) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    app = TzPlayerApp(auto_init=False)

    async def run_app() -> None:
        await app.store.initialize()
        playlist_id = await app.store.ensure_playlist("Default")
        files = [
            tmp_path / "moon_song.mp3",
            tmp_path / "sun_song.mp3",
        ]
        for path in files:
            path.write_bytes(b"")
        await app.store.add_tracks(playlist_id, files)
        async with app.run_test() as pilot:
            await asyncio.sleep(0)
            pane = app.query_one(PlaylistPane)
            await pane.configure(app.store, playlist_id, None)
            pane.focus_find()
            for key in "moon":
                await pilot.press(key)
            await asyncio.sleep(0.3)

            assert pane.search_active is True
            assert pane.total_count == 1
            pane.focus()
            await asyncio.sleep(0)
            assert app.focused is pane
            assert pane.has_find_text() is True

            await pilot.press("escape")
            await asyncio.sleep(0.1)
            assert pane.search_active is False
            assert pane.has_find_text() is False
            assert pane.total_count == 2
            assert app.focused is pane
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
            assert pane.query_one("#volume-spacer")
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


def test_status_pane_runtime_notice_is_visible_and_clearable() -> None:
    pane = StatusPane()

    class PaneApp(App):
        def compose(self) -> ComposeResult:
            yield pane

    app = PaneApp()

    async def run_app() -> None:
        async with app.run_test():
            await asyncio.sleep(0)
            pane.update_state(PlayerState(status="playing"))
            pane.set_runtime_notice("Visualizer switched to fallback.")
            rendered = str(pane._status_line.render())
            assert "Notice:" in rendered
            assert "Visualizer switched to fallback." in rendered

            pane.set_runtime_notice(None)
            rendered = str(pane._status_line.render())
            assert "Notice:" not in rendered
            assert "Status:" in rendered
            app.exit()

    _run(run_app())
