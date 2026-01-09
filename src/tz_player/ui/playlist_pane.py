"""Playlist pane with virtualized view."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Click, MouseScrollDown, MouseScrollUp
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, DataTable, Input, Select, Static

from tz_player.services.playlist_store import PlaylistRow, PlaylistStore
from tz_player.ui.modals.confirm import ConfirmModal
from tz_player.ui.modals.error import ErrorModal
from tz_player.ui.modals.path_input import PathInputModal

if TYPE_CHECKING:
    from tz_player.app import TzPlayerApp
    from tz_player.services.metadata_service import MetadataService

logger = logging.getLogger(__name__)

MEDIA_EXTENSIONS = {".mp3", ".flac", ".wav", ".m4a", ".ogg"}


class PlaylistPane(Static):
    """Playlist panel with actions and a virtualized table."""

    BINDINGS = [
        ("down", "cursor_down", "Down"),
        ("up", "cursor_up", "Up"),
        ("enter", "play_selected", "Play"),
        ("shift+up", "move_selection_up", "Move up"),
        ("shift+down", "move_selection_down", "Move down"),
        ("v", "toggle_selection", "Select"),
        ("delete", "remove_selected", "Remove"),
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
        self.metadata_service: MetadataService | None = None
        self._metadata_pending: set[int] = set()
        self._suspend_selection = False

        self._table: DataTable = DataTable(id="playlist-table")
        self._actions = Select(
            options=[
                ("Add files...", "add_files"),
                ("Add folder...", "add_folder"),
                ("Remove selected", "remove_selected"),
                ("Clear playlist", "clear_playlist"),
                ("Refresh metadata (selected)", "refresh_metadata_selected"),
                ("Refresh metadata (all)", "refresh_metadata_all"),
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

    async def on_click(self, event: Click) -> None:
        if event.widget is None:
            return
        if event.chain >= 2 and self._is_table_event(event.widget):
            app = cast("TzPlayerApp", self.app)
            self.run_worker(app.action_play_pause(), exclusive=True)
        if self._is_table_event(event.widget):
            self.focus()

    async def on_key(self, event) -> None:
        if event.key == "enter":
            event.stop()
            await self.action_play_selected()

    def _is_table_event(self, widget: Widget) -> bool:
        if widget is self._table:
            return True
        return self._table in widget.ancestors

    async def configure(
        self,
        store: PlaylistStore,
        playlist_id: int,
        playing_track_id: int | None,
        metadata_service: MetadataService | None = None,
    ) -> None:
        self.store = store
        self.playlist_id = playlist_id
        self.playing_track_id = playing_track_id
        self.metadata_service = metadata_service
        await self.refresh_view()

    def focus_find(self) -> None:
        self._find_input.focus()

    def get_cursor_track_id(self) -> int | None:
        if not self._rows:
            return None
        row_index = self._table.cursor_row
        if 0 <= row_index < len(self._rows):
            track_id = self._rows[row_index].track_id
            if track_id != self.cursor_track_id:
                self.cursor_track_id = track_id
                self._update_table()
            return track_id
        return self.cursor_track_id

    def set_playing_track_id(self, track_id: int | None) -> None:
        if track_id == self.playing_track_id:
            return
        self.playing_track_id = track_id
        self._update_table()

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
            self._request_visible_metadata()
        except Exception as exc:  # pragma: no cover - UI safety net
            logger.exception("Failed to refresh playlist: %s", exc)
            await self._show_error("Failed to refresh playlist. See log file.")

    async def _recompute_limit(self) -> None:
        await asyncio.sleep(0)
        visible = max(3, self._table.size.height - 2)
        self.limit = max(5, visible + 2)

    def _update_table(self) -> None:
        self._suspend_selection = True
        self._table.clear()
        for row in self._rows:
            marker = self._marker_for(row.track_id)
            if row.meta_valid:
                title = row.title or row.path.name
                artist = row.artist or ""
                album = row.album or ""
                duration = _format_duration(row.duration_ms)
            else:
                title = row.path.name
                artist = ""
                album = ""
                duration = ""
            self._table.add_row(
                marker,
                title,
                artist,
                album,
                duration,
            )
        if self.cursor_track_id is not None:
            for index, row in enumerate(self._rows):
                if row.track_id == self.cursor_track_id:
                    self._table.cursor_coordinate = (index, 0)
                    break
        self._suspend_selection = False
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

    async def action_play_selected(self) -> None:
        app = cast("TzPlayerApp", self.app)
        self.run_worker(app.action_play_selected(), exclusive=True)

    async def on_data_table_cell_selected(self, event: DataTable.CellSelected) -> None:
        if event.data_table is not self._table:
            return
        if self._suspend_selection:
            return
        row_index = event.coordinate.row
        if row_index < 0 or row_index >= len(self._rows):
            return
        track_id = self._rows[row_index].track_id
        self.cursor_track_id = track_id
        if event.coordinate.column == 0:
            await self.action_toggle_selection()
        else:
            self._update_table()

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
        elif action == "refresh_metadata_selected":
            self.run_worker(self._refresh_metadata_selected(), exclusive=True)
        elif action == "refresh_metadata_all":
            self.run_worker(self._refresh_metadata_all(), exclusive=True)

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

    async def _refresh_metadata_selected(self) -> None:
        if self.store is None or self.playlist_id is None:
            return
        if not self.selected_track_ids:
            return
        try:
            logger.info("Playlist action: refresh metadata (selected)")
            await self.store.invalidate_metadata(self.selected_track_ids)
            await self.refresh_view()
            self._metadata_pending.difference_update(self.selected_track_ids)
        except Exception as exc:
            logger.exception("Playlist action failed: %s", exc)
            await self._show_error("Action failed. See log file.")

    async def _refresh_metadata_all(self) -> None:
        if self.store is None or self.playlist_id is None:
            return
        try:
            logger.info("Playlist action: refresh metadata (all)")
            await self.store.invalidate_metadata()
            await self.refresh_view()
            self._metadata_pending.clear()
        except Exception as exc:
            logger.exception("Playlist action failed: %s", exc)
            await self._show_error("Action failed. See log file.")

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

    def _request_visible_metadata(self) -> None:
        if self.metadata_service is None:
            return
        needed = [row.track_id for row in self._rows if _needs_metadata(row)]
        pending = [
            track_id for track_id in needed if track_id not in self._metadata_pending
        ]
        if not pending:
            return
        self._metadata_pending.update(pending)
        self.run_worker(self._ensure_metadata(pending), exclusive=False)

    async def _ensure_metadata(self, track_ids: list[int]) -> None:
        if self.metadata_service is None:
            return
        try:
            await self.metadata_service.ensure_metadata(track_ids)
        finally:
            self._metadata_pending.difference_update(track_ids)


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


def _needs_metadata(row: PlaylistRow) -> bool:
    if row.meta_valid is None:
        return True
    if row.meta_valid is False:
        return row.meta_error is None
    return (
        row.title is None
        or row.artist is None
        or row.album is None
        or row.duration_ms is None
    )
