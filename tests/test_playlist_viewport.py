"""Tests for playlist viewport rendering and clamp helpers."""

from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual.geometry import Size

from tz_player.services.playlist_store import PlaylistRow
from tz_player.ui.playlist_pane import PlaylistPane
from tz_player.ui.playlist_viewport import PlaylistViewport


def test_offset_clamp_helpers() -> None:
    pane = PlaylistPane()
    pane.total_count = 10
    pane.limit = 4
    assert pane._max_offset() == 6
    assert pane._clamp_offset(-1) == 0
    assert pane._clamp_offset(2) == 2
    assert pane._clamp_offset(20) == 6


def test_viewport_single_cursor_marker(tmp_path: Path) -> None:
    rows = [
        PlaylistRow(
            item_id=1,
            track_id=5,
            pos_key=1,
            path=tmp_path / "one.mp3",
            title="One",
            artist="",
            album=None,
            year=None,
            duration_ms=None,
            meta_valid=True,
            meta_error=None,
        ),
        PlaylistRow(
            item_id=2,
            track_id=5,
            pos_key=2,
            path=tmp_path / "two.mp3",
            title="Two",
            artist="",
            album=None,
            year=None,
            duration_ms=None,
            meta_valid=True,
            meta_error=None,
        ),
    ]
    viewport = PlaylistViewport()
    viewport.update_model(
        rows=rows,
        total_count=2,
        offset=0,
        limit=2,
        cursor_item_id=2,
        selected_item_ids=set(),
        playing_item_id=None,
    )
    viewport._size = Size(30, 2)
    rendered = viewport.render()
    assert isinstance(rendered, Text)
    lines = rendered.plain.splitlines()
    assert len(lines) == 2
    assert sum(1 for line in lines if line.startswith(">")) == 1
