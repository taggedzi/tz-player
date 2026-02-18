"""Tests for metadata debounce behavior."""

from __future__ import annotations

import asyncio

import tz_player.app as app_module
import tz_player.paths as paths
from tz_player.app import TzPlayerApp
from tz_player.ui.playlist_pane import PlaylistPane


def _run(coro):
    """Run async debounce scenario from sync tests."""
    return asyncio.run(coro)


def test_mark_metadata_done() -> None:
    pane = PlaylistPane()
    pane._metadata_pending.update({1, 2, 3})
    pane.mark_metadata_done([2, 4])
    assert pane._metadata_pending == {1, 3}


def test_metadata_debounce_reschedules(tmp_path, monkeypatch) -> None:
    class FakeAppDirs:
        def __init__(self, data_dir, config_dir) -> None:
            self.user_data_dir = str(data_dir)
            self.user_config_dir = str(config_dir)

    def fake_app_dirs(app_name: str, appauthor: bool | None = None) -> FakeAppDirs:
        return FakeAppDirs(tmp_path / "data", tmp_path / "config")

    monkeypatch.setattr(paths, "AppDirs", fake_app_dirs)
    paths.get_app_dirs.cache_clear()

    class FakePane:
        def __init__(self) -> None:
            self.updated: list[set[int]] = []

        def mark_metadata_done(self, track_ids: list[int]) -> None:
            return

        def get_visible_track_ids(self) -> set[int]:
            return {1, 2, 3}

        async def refresh_visible_rows(self, updated_track_ids: set[int]) -> None:
            self.updated.append(set(updated_track_ids))

    async def run_debounce() -> tuple[list[set[int]], set[int]]:
        app = TzPlayerApp(auto_init=False)
        fake = FakePane()
        monkeypatch.setattr(app_module, "METADATA_REFRESH_DEBOUNCE", 0.0)
        app.query_one = lambda *args, **kwargs: fake  # type: ignore[assignment]
        app._metadata_pending_ids = {1, 2}
        task = asyncio.create_task(app._refresh_metadata_debounced())
        await asyncio.sleep(0)
        app._metadata_pending_ids.add(3)
        await task
        if app._metadata_refresh_task is not None:
            await app._metadata_refresh_task
        return fake.updated, app._metadata_pending_ids

    updated, pending = _run(run_debounce())
    assert pending == set()
    assert any(3 in batch for batch in updated)
