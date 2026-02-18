"""Tests for playlist viewport rendering and clamp helpers."""

from __future__ import annotations

import asyncio
from pathlib import Path

from rich.text import Text
from textual.geometry import Offset, Size
from textual.message import Message

from tz_player.events import (
    PlaylistJumpRequested,
    PlaylistRowClicked,
    PlaylistRowDoubleClicked,
    PlaylistScrollRequested,
)
from tz_player.services.playlist_store import PlaylistRow
from tz_player.ui.playlist_pane import PlaylistPane
from tz_player.ui.playlist_viewport import PlaylistViewport


class _FakeScrollEvent:
    """Scroll event stub that tracks whether propagation was stopped."""

    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class _FakeClickEvent:
    """Click event stub exposing fixed content offset and click-chain count."""

    def __init__(self, offset: Offset, chain: int = 1) -> None:
        self._offset = offset
        self.chain = chain

    def get_content_offset(self, _widget) -> Offset:
        return self._offset


class _FakeMouseDownEvent:
    """Mouse-down stub used for scrollbar interaction tests."""

    def __init__(self, offset: Offset) -> None:
        self._offset = offset
        self.stopped = False

    def get_content_offset(self, _widget) -> Offset:
        return self._offset

    def stop(self) -> None:
        self.stopped = True


class _FakeMouseMoveEvent:
    """Mouse-move stub returning captured offset for drag tests."""

    def __init__(self, offset: Offset) -> None:
        self._offset = offset
        self.stopped = False

    def get_content_offset_capture(self, _widget) -> Offset:
        return self._offset

    def stop(self) -> None:
        self.stopped = True


class _FakeMouseMoveNoneEvent:
    """Mouse-move stub that simulates missing capture offset."""

    def __init__(self) -> None:
        self.stopped = False

    def get_content_offset_capture(self, _widget):  # type: ignore[no-untyped-def]
        return None

    def stop(self) -> None:
        self.stopped = True


class _SizedViewport(PlaylistViewport):
    """Viewport test double with deterministic fixed size."""

    @property
    def size(self) -> Size:  # type: ignore[override]
        return Size(10, 5)


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


def test_viewport_mouse_scroll_posts_scroll_request() -> None:
    viewport = PlaylistViewport()
    emitted: list[Message] = []
    viewport.post_message = emitted.append  # type: ignore[assignment]
    down_event = _FakeScrollEvent()
    up_event = _FakeScrollEvent()

    async def run() -> None:
        await viewport.on_mouse_scroll_down(down_event)  # type: ignore[arg-type]
        await viewport.on_mouse_scroll_up(up_event)  # type: ignore[arg-type]

    asyncio.run(run())
    assert down_event.stopped is True
    assert up_event.stopped is True
    assert len(emitted) == 2
    assert isinstance(emitted[0], PlaylistScrollRequested)
    assert emitted[0].delta == 1
    assert isinstance(emitted[1], PlaylistScrollRequested)
    assert emitted[1].delta == -1


def test_viewport_click_posts_row_click_and_double_click(tmp_path: Path) -> None:
    rows = [
        PlaylistRow(
            item_id=7,
            track_id=7,
            pos_key=1,
            path=tmp_path / "one.mp3",
            title="One",
            artist="",
            album=None,
            year=None,
            duration_ms=None,
            meta_valid=True,
            meta_error=None,
        )
    ]
    viewport = _SizedViewport()
    emitted: list[Message] = []
    viewport._handle_scrollbar_click = lambda _offset: False  # type: ignore[assignment]

    async def run() -> None:
        viewport.update_model(
            rows=rows,
            total_count=1,
            offset=0,
            limit=1,
            cursor_item_id=7,
            selected_item_ids=set(),
            playing_item_id=None,
        )
        viewport.post_message = emitted.append  # type: ignore[assignment]
        await viewport.on_click(_FakeClickEvent(Offset(0, 0), chain=1))  # type: ignore[arg-type]
        await viewport.on_click(_FakeClickEvent(Offset(0, 0), chain=2))  # type: ignore[arg-type]

    asyncio.run(run())
    assert len(emitted) == 2
    assert isinstance(emitted[0], PlaylistRowClicked)
    assert emitted[0].item_id == 7
    assert isinstance(emitted[1], PlaylistRowDoubleClicked)
    assert emitted[1].item_id == 7


def test_viewport_scrollbar_drag_posts_jump_request() -> None:
    viewport = _SizedViewport()
    emitted: list[Message] = []

    async def run() -> None:
        viewport.update_model(total_count=20, limit=5, offset=0)
        viewport.post_message = emitted.append  # type: ignore[assignment]
        scrollbar_x = viewport.size.width - 1
        mouse_down = _FakeMouseDownEvent(Offset(scrollbar_x, viewport.size.height // 2))
        mouse_move = _FakeMouseMoveEvent(Offset(scrollbar_x, viewport.size.height - 1))
        await viewport.on_mouse_down(mouse_down)  # type: ignore[arg-type]
        await viewport.on_mouse_move(mouse_move)  # type: ignore[arg-type]
        assert mouse_down.stopped is True
        assert mouse_move.stopped is True

    asyncio.run(run())
    assert len(emitted) == 2
    assert isinstance(emitted[0], PlaylistJumpRequested)
    assert emitted[0].offset == 8
    assert isinstance(emitted[1], PlaylistJumpRequested)
    assert emitted[1].offset == 15


def test_viewport_mouse_move_with_lost_capture_is_ignored() -> None:
    viewport = _SizedViewport()
    emitted: list[Message] = []
    viewport.post_message = emitted.append  # type: ignore[assignment]
    viewport._dragging_scrollbar = True  # noqa: SLF001
    event = _FakeMouseMoveNoneEvent()

    async def run() -> None:
        await viewport.on_mouse_move(event)  # type: ignore[arg-type]

    asyncio.run(run())
    assert emitted == []
    assert event.stopped is False
