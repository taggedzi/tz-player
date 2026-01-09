"""Custom viewport widget for rendering playlist rows."""

from __future__ import annotations

from dataclasses import dataclass

from rich.text import Text
from textual.events import Click, MouseDown, MouseMove, MouseScrollDown, MouseScrollUp, MouseUp
from textual.geometry import Offset
from textual.widget import Widget

from tz_player.events import (
    PlaylistJumpRequested,
    PlaylistRowClicked,
    PlaylistRowDoubleClicked,
    PlaylistScrollRequested,
)
from tz_player.services.playlist_store import PlaylistRow


@dataclass
class ViewportModel:
    rows: list[PlaylistRow]
    total_count: int
    offset: int
    limit: int
    cursor_item_id: int | None
    selected_item_ids: set[int]
    playing_item_id: int | None


class PlaylistViewport(Widget):
    """Render-only playlist viewport with a manual scrollbar."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.can_focus = True
        self._model = ViewportModel(
            rows=[],
            total_count=0,
            offset=0,
            limit=0,
            cursor_item_id=None,
            selected_item_ids=set(),
            playing_item_id=None,
        )
        self._dragging_scrollbar = False

    def update_model(self, **kwargs) -> None:
        for key, value in kwargs.items():
            setattr(self._model, key, value)
        self.refresh()

    def render(self) -> Text:
        width = max(1, self.size.width)
        height = max(1, self.size.height)
        text_width = max(0, width - 1)

        scroll_chars = _render_scrollbar(
            height,
            self._model.total_count,
            self._model.limit,
            self._model.offset,
        )

        lines: list[str] = []
        for idx in range(height):
            if idx < len(self._model.rows):
                row = self._model.rows[idx]
                marker = _marker_for(
                    row.item_id,
                    self._model.cursor_item_id,
                    self._model.selected_item_ids,
                    self._model.playing_item_id,
                )
                title = _title_for(row)
                artist = row.artist or ""
                if artist:
                    content = f"{title} - {artist}"
                else:
                    content = title
                line = _truncate(f"{marker} {content}", text_width)
            else:
                line = "".ljust(text_width)
            lines.append(f"{line}{scroll_chars[idx]}")
        return Text("\n".join(lines))

    async def on_mouse_scroll_down(self, event: MouseScrollDown) -> None:
        event.stop()
        self.post_message(PlaylistScrollRequested(1))

    async def on_mouse_scroll_up(self, event: MouseScrollUp) -> None:
        event.stop()
        self.post_message(PlaylistScrollRequested(-1))

    async def on_click(self, event: Click) -> None:
        offset = event.get_content_offset(self)
        if offset is None:
            return
        if self._handle_scrollbar_click(offset):
            return
        row_index = offset.y
        if row_index < 0 or row_index >= len(self._model.rows):
            return
        item_id = self._model.rows[row_index].item_id
        if event.chain >= 2:
            self.post_message(PlaylistRowDoubleClicked(item_id))
            return
        self.post_message(PlaylistRowClicked(item_id))

    async def on_mouse_down(self, event: MouseDown) -> None:
        offset = event.get_content_offset(self)
        if offset is None:
            return
        if self._handle_scrollbar_click(offset):
            self._dragging_scrollbar = True
            event.stop()

    async def on_mouse_up(self, event: MouseUp) -> None:
        self._dragging_scrollbar = False

    async def on_mouse_move(self, event: MouseMove) -> None:
        if not self._dragging_scrollbar:
            return
        offset = event.get_content_offset_capture(self)
        self._emit_scroll_jump(offset.y)
        event.stop()

    def _handle_scrollbar_click(self, offset: Offset) -> bool:
        width = max(1, self.size.width)
        if offset.x != width - 1:
            return False
        self._emit_scroll_jump(offset.y)
        return True

    def _emit_scroll_jump(self, y: int) -> None:
        height = max(1, self.size.height)
        max_offset = max(0, self._model.total_count - self._model.limit)
        if max_offset == 0:
            return
        ratio = min(max(y / max(1, height - 1), 0.0), 1.0)
        target = int(round(ratio * max_offset))
        self.post_message(PlaylistJumpRequested(target))


def _marker_for(
    item_id: int,
    cursor_item_id: int | None,
    selected_item_ids: set[int],
    playing_item_id: int | None,
) -> str:
    marker = ""
    if item_id == playing_item_id:
        marker += "▶"
    if item_id == cursor_item_id:
        marker += ">"
    if item_id in selected_item_ids:
        marker += "✓"
    return marker or " "


def _title_for(row: PlaylistRow) -> str:
    if row.meta_valid:
        return row.title or row.path.name
    return row.path.name


def _truncate(value: str, width: int) -> str:
    if width <= 0:
        return ""
    if len(value) <= width:
        return value.ljust(width)
    if width <= 3:
        return value[:width]
    return f"{value[: width - 3]}..."


def _render_scrollbar(
    height: int, total_count: int, limit: int, offset: int
) -> list[str]:
    if height <= 0:
        return []
    max_offset = max(0, total_count - limit)
    if total_count <= 0 or limit <= 0:
        return ["│" for _ in range(height)]
    thumb_size = max(1, int(round(height * (limit / max(total_count, 1)))))
    if max_offset == 0:
        thumb_top = 0
    else:
        thumb_top = int(round((height - thumb_size) * (offset / max_offset)))
    chars = []
    for idx in range(height):
        if thumb_top <= idx < thumb_top + thumb_size:
            chars.append("█")
        else:
            chars.append("│")
    return chars
