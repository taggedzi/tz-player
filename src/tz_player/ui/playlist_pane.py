"""Playlist pane with virtualized view."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Literal

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import MouseScrollDown, MouseScrollUp
from textual.message import Message
from textual.widgets import Button, DataTable, Input, Select, Static

from tz_player.services.playlist_store import PlaylistRow, PlaylistStore
from tz_player.ui.modals.confirm import ConfirmModal
from tz_player.ui.modals.error import ErrorModal
from tz_player.ui.modals.path_input import PathInputModal

logger = logging.getLogger(__name__)

MEDIA_EXTENSIONS = {".mp3", ".flac", ".wav", ".m4a", ".ogg"}


class PlaylistPane(Static):
    """Playlist panel with actions and a virtualized table."""

    BINDINGS = [
        ("down", "cursor_down", "Down"),
        ("up", "cursor_up", "Up"),
        ("shift+up", "move_selection_up", "Move up"),
        ("shift+down", "move_selection_down", "Move down"),
        ("s", "toggle_selection", "Select"),
        ("x", "remove_selected", "Remove"),
    ]

    class SelectionChanged(Message):
        def __init__(self, selected_count: int) -> None:
            super().__init__()
            self.selected_count = selected_count

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.can_focus = True
        self.store: PlaylistStore | None = None
        self.playlist_id: int | None = None
        self.cursor_track_id: int | None = None
        self.playing_track_id: int | None = None
        self.selected_track_ids: set[int] = set()
        self.total_count = 0
        self.window_offset = 0
        self.limit = 10
        self._rows: list[PlaylistRow] = []

        self._table: DataTable = DataTable(id="playlist-table")
        self._actions = Select(
            options=[
                ("Add files...", "add_files"),
                ("Add folder...", "add_folder"),
                ("Remove selected", "remove_selected"),
                ("Clear playlist", "clear_playlist"),
            ],
            prompt="Actions",
            id="playlist-actions",
        )
        self._find_input = Input(placeholder="Find...", id="playlist-find")
        self._count_label = Static("0 tracks", id="playlist-count")

    def compose(self) -> ComposeResult:
        yield Vertical(
            Horizontal(
                self._actions,
                Button("Up", id="reorder-up"),
                Button("Down", id="reorder-down"),
                self._find_input,
                id="playlist-top",
            ),
            self._table,
            Horizontal(
                self._count_label,
                Static("Repeat: off", id="repeat-placeholder"),
                Static("Shuffle: off", id="shuffle-placeholder"),
                Static("Transport: --:--", id="transport-placeholder"),
                id="playlist-bottom",
            ),
            id="playlist-pane",
        )

    def on_mount(self) -> None:
        self._table.add_columns(" ", "Title", "Artist", "Album", "Duration")
        self._table.show_header = True

    async def on_resize(self) -> None:
        if self.store is None or self.playlist_id is None:
            return
        await self.refresh_view()

    async def on_mouse_scroll_down(self, event: MouseScrollDown) -> None:
        event.stop()
        await self._scroll(1)

    async def on_mouse_scroll_up(self, event: MouseScrollUp) -> None:
        event.stop()
        await self._scroll(-1)

    async def configure(
        self, store: PlaylistStore, playlist_id: int, playing_track_id: int | None
    ) -> None:
        self.store = store
        self.playlist_id = playlist_id
        self.playing_track_id = playing_track_id
        await self.refresh_view()

    def focus_find(self) -> None:
        self._find_input.focus()

    async def refresh_view(self) -> None:
        if self.store is None or self.playlist_id is None:
            return
        await self._recompute_limit()
        try:
            self.total_count = await self.store.count(self.playlist_id)
            self.window_offset = max(
                0, min(self.window_offset, max(0, self.total_count - 1))
            )
            self._rows = await self.store.fetch_window(
                self.playlist_id, self.window_offset, self.limit
            )
            if self.cursor_track_id is None and self._rows:
                self.cursor_track_id = self._rows[0].track_id
            self._update_table()
        except Exception as exc:  # pragma: no cover - UI safety net
            logger.exception("Failed to refresh playlist: %s", exc)
            await self._show_error("Failed to refresh playlist. See log file.")

    async def _recompute_limit(self) -> None:
        await asyncio.sleep(0)
        visible = max(3, self._table.size.height - 2)
        self.limit = max(5, visible + 2)

    def _update_table(self) -> None:
        self._table.clear()
        for row in self._rows:
            marker = self._marker_for(row.track_id)
            title = row.title or row.path.name
            self._table.add_row(
                marker,
                title,
                row.artist or "",
                row.album or "",
                _format_duration(row.duration_ms),
            )
        self._count_label.update(f"{self.total_count} tracks")

    def _marker_for(self, track_id: int) -> str:
        marker = ""
        if track_id == self.playing_track_id:
            marker += "▶"
        if track_id == self.cursor_track_id:
            marker += ">"
        if track_id in self.selected_track_ids:
            marker += "✓"
        return marker or " "

    async def action_cursor_down(self) -> None:
        await self._move_cursor(1)

    async def action_cursor_up(self) -> None:
        await self._move_cursor(-1)

    async def _move_cursor(self, delta: int) -> None:
        if not self._rows:
            return
        track_ids = [row.track_id for row in self._rows]
        if self.cursor_track_id not in track_ids:
            self.cursor_track_id = track_ids[0]
            self._update_table()
            return
        idx = track_ids.index(self.cursor_track_id)
        next_idx = idx + delta
        if 0 <= next_idx < len(track_ids):
            self.cursor_track_id = track_ids[next_idx]
            self._update_table()
            return
        new_offset = self.window_offset + delta
        if new_offset < 0 or new_offset >= self.total_count:
            return
        self.window_offset = new_offset
        await self.refresh_view()

    async def _scroll(self, delta: int) -> None:
        if self.total_count == 0:
            return
        new_offset = max(
            0, min(self.window_offset + delta, max(0, self.total_count - 1))
        )
        if new_offset == self.window_offset:
            return
        self.window_offset = new_offset
        await self.refresh_view()

    async def action_move_selection_up(self) -> None:
        await self._move_selection("up")

    async def action_move_selection_down(self) -> None:
        await self._move_selection("down")

    async def action_remove_selected(self) -> None:
        self.run_worker(self._remove_selected(), exclusive=True)

    async def _move_selection(self, direction: Literal["up", "down"]) -> None:
        if self.store is None or self.playlist_id is None:
            return
        try:
            await self.store.move_selection(
                self.playlist_id,
                direction,
                sorted(self.selected_track_ids),
                self.cursor_track_id,
            )
            await self.refresh_view()
        except Exception as exc:
            logger.exception("Failed to reorder: %s", exc)
            await self._show_error("Failed to reorder selection. See log file.")

    async def action_toggle_selection(self) -> None:
        if self.cursor_track_id is None:
            return
        if self.cursor_track_id in self.selected_track_ids:
            self.selected_track_ids.remove(self.cursor_track_id)
        else:
            self.selected_track_ids.add(self.cursor_track_id)
        self._update_table()
        self.post_message(self.SelectionChanged(len(self.selected_track_ids)))

    async def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "playlist-actions":
            return
        action = event.value
        if action is None:
            return
        event.select.clear()
        if action == "add_files":
            self.run_worker(self._add_files(), exclusive=True)
        elif action == "add_folder":
            self.run_worker(self._add_folder(), exclusive=True)
        elif action == "remove_selected":
            self.run_worker(self._remove_selected(), exclusive=True)
        elif action == "clear_playlist":
            self.run_worker(self._clear_playlist(), exclusive=True)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "reorder-up":
            await self._move_selection("up")
        elif event.button.id == "reorder-down":
            await self._move_selection("down")

    async def _add_files(self) -> None:
        if self.store is None:
            return
        result = await self._prompt_path(
            "Add files (separate with ';')", placeholder="C:\\music\\a.mp3; D:\\b.flac"
        )
        if not result:
            return
        paths = _parse_paths(result)
        if not paths:
            return
        await self._run_store_action("add files", self.store.add_tracks, paths)

    async def _add_folder(self) -> None:
        if self.store is None:
            return
        result = await self._prompt_path("Add folder", placeholder="C:\\music")
        if not result:
            return
        folder = Path(result).expanduser()
        paths = await asyncio.to_thread(_scan_media_files, folder)
        if not paths:
            await self._show_error("No media files found in folder.")
            return
        await self._run_store_action("add folder", self.store.add_tracks, paths)

    async def _remove_selected(self) -> None:
        if self.store is None:
            return
        if not self.selected_track_ids:
            return
        confirmed = await self._confirm("Remove selected tracks?")
        if not confirmed:
            return
        await self._run_store_action(
            "remove selected", self.store.remove_tracks, self.selected_track_ids
        )
        self.selected_track_ids.clear()

    async def _clear_playlist(self) -> None:
        if self.store is None:
            return
        confirmed = await self._confirm("Clear the playlist?")
        if not confirmed:
            return
        await self._run_store_action("clear playlist", self.store.clear_playlist)
        self.selected_track_ids.clear()

    async def _run_store_action(self, label: str, func, *args) -> None:
        if self.store is None or self.playlist_id is None:
            return
        try:
            logger.info("Playlist action: %s", label)
            await func(self.playlist_id, *args)
            await self.refresh_view()
        except Exception as exc:
            logger.exception("Playlist action failed: %s", exc)
            await self._show_error("Action failed. See log file.")

    async def _confirm(self, message: str) -> bool:
        result = await self.app.push_screen_wait(ConfirmModal(message))
        return bool(result)

    async def _prompt_path(self, title: str, placeholder: str = "") -> str | None:
        return await self.app.push_screen_wait(
            PathInputModal(title, placeholder=placeholder)
        )

    async def _show_error(self, message: str) -> None:
        self.app.push_screen(ErrorModal(message))


def _parse_paths(text: str) -> list[Path]:
    parts = [part.strip().strip('"') for part in text.replace("\n", ";").split(";")]
    return [Path(part) for part in parts if part]


def _scan_media_files(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    files: list[Path] = []
    for path in folder.rglob("*"):
        if path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS:
            files.append(path)
    return files


def _format_duration(duration_ms: int | None) -> str:
    if not duration_ms:
        return ""
    seconds = duration_ms // 1000
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes}:{seconds:02d}"
