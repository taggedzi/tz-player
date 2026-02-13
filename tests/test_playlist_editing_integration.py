"""Integration tests for playlist editing workflows."""

from __future__ import annotations

import asyncio
from pathlib import Path

import tz_player.paths as paths
from tz_player.app import TzPlayerApp
from tz_player.ui.actions_menu import ActionsMenuSelected
from tz_player.ui.playlist_pane import PlaylistPane


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


async def _configure_playlist(
    app: TzPlayerApp,
    tmp_path: Path,
    *,
    names: list[str],
) -> tuple[PlaylistPane, int]:
    await app.store.initialize()
    playlist_id = await app.store.ensure_playlist("Default")
    files = [tmp_path / name for name in names]
    for path in files:
        path.write_bytes(b"")
    await app.store.add_tracks(playlist_id, files)
    pane = app.query_one(PlaylistPane)
    await pane.configure(app.store, playlist_id, None)
    return pane, playlist_id


def test_keyboard_reorder_selected_item(tmp_path, monkeypatch) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    app = TzPlayerApp(auto_init=False)

    async def run_app() -> None:
        async with app.run_test() as pilot:
            await asyncio.sleep(0)
            pane, _playlist_id = await _configure_playlist(
                app,
                tmp_path,
                names=["track1.mp3", "track2.mp3", "track3.mp3"],
            )

            assert [row.path.name for row in pane._rows] == [
                "track1.mp3",
                "track2.mp3",
                "track3.mp3",
            ]
            await pilot.press("down")
            await asyncio.sleep(0)
            await pilot.press("v")
            await asyncio.sleep(0)
            await pilot.press("shift+down")
            await asyncio.sleep(0)

            assert [row.path.name for row in pane._rows] == [
                "track1.mp3",
                "track3.mp3",
                "track2.mp3",
            ]
            app.exit()

    _run(run_app())


def test_remove_selected_respects_confirm_and_cancel(tmp_path, monkeypatch) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    app = TzPlayerApp(auto_init=False)

    async def run_app() -> None:
        async with app.run_test() as pilot:
            await asyncio.sleep(0)
            pane, playlist_id = await _configure_playlist(
                app,
                tmp_path,
                names=["track1.mp3", "track2.mp3"],
            )

            tasks = []

            def run_worker(coro, exclusive=False):  # type: ignore[no-untyped-def]
                task = asyncio.create_task(coro)
                tasks.append(task)
                return task

            pane.run_worker = run_worker  # type: ignore[assignment]

            await pilot.press("v")
            await asyncio.sleep(0)
            assert len(pane.selected_item_ids) == 1

            async def confirm_false(_message: str) -> bool:
                return False

            pane._confirm = confirm_false  # type: ignore[assignment]
            await pilot.press("delete")
            if tasks:
                await asyncio.gather(*tasks)
                tasks.clear()

            assert await app.store.count(playlist_id) == 2
            assert len(pane.selected_item_ids) == 1

            async def confirm_true(_message: str) -> bool:
                return True

            pane._confirm = confirm_true  # type: ignore[assignment]
            await pilot.press("delete")
            if tasks:
                await asyncio.gather(*tasks)
                tasks.clear()

            assert await app.store.count(playlist_id) == 1
            assert pane.selected_item_ids == set()
            app.exit()

    _run(run_app())


def test_add_files_action_parses_paths_and_updates_playlist(
    tmp_path, monkeypatch
) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    app = TzPlayerApp(auto_init=False)

    async def run_app() -> None:
        async with app.run_test():
            await asyncio.sleep(0)
            await app.store.initialize()
            playlist_id = await app.store.ensure_playlist("Default")
            pane = app.query_one(PlaylistPane)
            await pane.configure(app.store, playlist_id, None)

            file_a = tmp_path / "added_a.mp3"
            file_b = tmp_path / "added_b.flac"
            file_a.write_bytes(b"")
            file_b.write_bytes(b"")

            async def prompt_path(_title: str, placeholder: str = "") -> str:
                assert placeholder
                return f'"{file_a}";\n{file_b}'

            tasks = []

            def run_worker(coro, exclusive=False):  # type: ignore[no-untyped-def]
                task = asyncio.create_task(coro)
                tasks.append(task)
                return task

            pane._prompt_path = prompt_path  # type: ignore[assignment]
            pane.run_worker = run_worker  # type: ignore[assignment]
            await app.on_actions_menu_selected(ActionsMenuSelected("add_files"))
            if tasks:
                await asyncio.gather(*tasks)

            assert await app.store.count(playlist_id) == 2
            rows = await app.store.fetch_window(playlist_id, 0, 10)
            assert [row.path.name for row in rows] == ["added_a.mp3", "added_b.flac"]
            app.exit()

    _run(run_app())
