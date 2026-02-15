"""Regression tests for non-blocking IO path contracts."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import tz_player.services.metadata_service as metadata_service_module
import tz_player.ui.playlist_pane as playlist_pane_module
from tz_player.ui.playlist_pane import PlaylistPane
from tz_player.utils.async_utils import run_blocking


def _run(coro):
    return asyncio.run(coro)


def test_metadata_safe_stat_uses_run_blocking(monkeypatch, tmp_path) -> None:
    calls: list[tuple[object, tuple[object, ...]]] = []

    class FakeStat:
        st_mtime_ns = 123
        st_size = 456

    async def fake_run_blocking(func, /, *args, **kwargs):
        calls.append((func, args))
        return FakeStat()

    monkeypatch.setattr(metadata_service_module, "run_blocking", fake_run_blocking)

    path = tmp_path / "track.mp3"
    stat = _run(metadata_service_module._safe_stat(path))

    assert stat is not None
    assert stat.mtime_ns == 123
    assert stat.size_bytes == 456
    assert len(calls) == 1
    func, args = calls[0]
    assert getattr(func, "__name__", "") == "stat"
    assert args == ()


def test_run_blocking_rejects_non_callable() -> None:
    with pytest.raises(TypeError, match="func must be callable"):
        _run(run_blocking(None))  # type: ignore[arg-type]


def test_add_folder_scans_via_run_blocking(monkeypatch, tmp_path) -> None:
    pane = PlaylistPane()

    class FakeStore:
        async def add_tracks(self, playlist_id: int, paths: list[Path]) -> int:
            del playlist_id, paths
            return 0

    pane.store = FakeStore()  # type: ignore[assignment]
    folder = tmp_path / "music"
    folder.mkdir(parents=True, exist_ok=True)
    track = folder / "song.mp3"
    track.write_bytes(b"")

    calls: list[tuple[object, tuple[object, ...]]] = []
    added: dict[str, object] = {}

    async def fake_run_blocking(func, /, *args, **kwargs):
        calls.append((func, args))
        return func(*args, **kwargs)

    async def fake_prompt_path(title: str, placeholder: str = "") -> str:
        del title, placeholder
        return str(folder)

    async def fake_run_store_action(label: str, func, *args) -> None:  # type: ignore[no-untyped-def]
        added["label"] = label
        added["func"] = func
        added["args"] = args

    monkeypatch.setattr(playlist_pane_module, "run_blocking", fake_run_blocking)
    pane._prompt_path = fake_prompt_path  # type: ignore[assignment]
    pane._run_store_action = fake_run_store_action  # type: ignore[assignment]

    _run(pane._add_folder())

    assert len(calls) == 1
    func, args = calls[0]
    assert func is playlist_pane_module._scan_media_files
    assert args == (Path(folder),)
    assert added["label"] == "add folder"
    paths = added["args"][0]
    assert paths == [track]
