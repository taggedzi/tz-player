"""Playlist pane with virtualized view."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Input, Static

from tz_player.events import (
    PlaylistJumpRequested,
    PlaylistRowClicked,
    PlaylistRowDoubleClicked,
    PlaylistScrollRequested,
)
from tz_player.services.playlist_store import PlaylistRow, PlaylistStore
from tz_player.ui.actions_menu import (
    ActionsMenuButton,
    ActionsMenuDismissed,
    ActionsMenuPopup,
    ActionsMenuSelected,
)
from tz_player.ui.modals.confirm import ConfirmModal
from tz_player.ui.modals.error import ErrorModal
from tz_player.ui.modals.path_input import PathInputModal
from tz_player.ui.playlist_viewport import PlaylistViewport
from tz_player.ui.text_button import TextButton, TextButtonPressed
from tz_player.ui.transport_controls import (
    ToggleRepeat,
    ToggleShuffle,
    TransportAction,
    TransportControls,
)

if TYPE_CHECKING:
    from tz_player.app import TzPlayerApp
    from tz_player.services.metadata_service import MetadataService
    from tz_player.services.player_service import PlayerState

logger = logging.getLogger(__name__)

MEDIA_EXTENSIONS = {".mp3", ".flac", ".wav", ".m4a", ".ogg"}
DEBUG_VIEWPORT = False


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
        self.cursor_item_id: int | None = None
        self.playing_item_id: int | None = None
        self.selected_item_ids: set[int] = set()
        self.total_count = 0
        self.window_offset = 0
        self.limit = 10
        self._rows: list[PlaylistRow] = []
        self.metadata_service: MetadataService | None = None
        self._metadata_pending: set[int] = set()
        self._viewport = PlaylistViewport(id="playlist-viewport")
        self._actions = ActionsMenuButton(id="playlist-actions")
        self._actions_popup: ActionsMenuPopup | None = None
        self._find_input = Input(placeholder="Find...", id="playlist-find")
        self._transport_controls = TransportControls(id="playlist-bottom")
        self._last_player_state: PlayerState | None = None

    def compose(self) -> ComposeResult:
        yield Vertical(
            Horizontal(
                self._actions,
                TextButton("Up", action="reorder_up", id="reorder-up"),
                TextButton("Down", action="reorder_down", id="reorder-down"),
                self._find_input,
                id="playlist-top",
            ),
            self._viewport,
            self._transport_controls,
            id="playlist-pane",
        )

    def on_mount(self) -> None:
        self.limit = max(1, self._viewport.size.height)
        self._update_viewport()

    async def on_resize(self) -> None:
        if self.store is None or self.playlist_id is None:
            return
        await self.refresh_view()

    async def on_playlist_row_clicked(self, event: PlaylistRowClicked) -> None:
        self.cursor_item_id = event.item_id
        self._update_viewport()
        await self._refresh_transport_controls()
        self.focus()

    async def on_playlist_row_double_clicked(
        self, event: PlaylistRowDoubleClicked
    ) -> None:
        app = cast("TzPlayerApp", self.app)
        self.run_worker(app.action_play_pause(), exclusive=True)

    async def on_playlist_scroll_requested(
        self, event: PlaylistScrollRequested
    ) -> None:
        await self._scroll(event.delta)

    async def on_playlist_jump_requested(self, event: PlaylistJumpRequested) -> None:
        target = self._clamp_offset(event.offset)
        if target == self.window_offset:
            return
        self.window_offset = target
        await self._refresh_window()

    async def configure(
        self,
        store: PlaylistStore,
        playlist_id: int,
        playing_item_id: int | None,
        metadata_service: MetadataService | None = None,
    ) -> None:
        self.store = store
        self.playlist_id = playlist_id
        self.playing_item_id = playing_item_id
        self.metadata_service = metadata_service
        await self.refresh_view()

    def focus_find(self) -> None:
        self._find_input.focus()

    def get_cursor_item_id(self) -> int | None:
        if self.cursor_item_id is None and self._rows:
            self.cursor_item_id = self._rows[0].item_id
            self._update_viewport()
        return self.cursor_item_id

    def get_visible_track_ids(self) -> set[int]:
        return {row.track_id for row in self._rows}

    def get_visible_item_ids(self) -> set[int]:
        return {row.item_id for row in self._rows}

    def mark_metadata_done(self, track_ids: list[int]) -> None:
        self._metadata_pending.difference_update(track_ids)

    def set_playing_item_id(self, item_id: int | None) -> None:
        if item_id == self.playing_item_id:
            return
        self.playing_item_id = item_id
        self._update_viewport()

    async def update_transport_controls(self, state: PlayerState) -> None:
        self._last_player_state = state
        await self._refresh_transport_controls()

    async def on_transport_action(self, event: TransportAction) -> None:
        app = cast("TzPlayerApp", self.app)
        if event.action == "prev":
            self.run_worker(app.action_previous_track(), exclusive=False)
        elif event.action == "toggle_play":
            self.run_worker(app.action_play_pause(), exclusive=False)
        elif event.action == "stop":
            self.run_worker(app.action_stop(), exclusive=False)
        elif event.action == "next":
            self.run_worker(app.action_next_track(), exclusive=False)

    async def on_toggle_repeat(self, event: ToggleRepeat) -> None:
        app = cast("TzPlayerApp", self.app)
        self.run_worker(app.action_repeat_mode(), exclusive=False)
        event.stop()

    async def on_toggle_shuffle(self, event: ToggleShuffle) -> None:
        app = cast("TzPlayerApp", self.app)
        self.run_worker(app.action_shuffle(), exclusive=False)
        event.stop()

    async def _refresh_transport_controls(self) -> None:
        if self._last_player_state is None:
            return
        if self.store is None or self.playlist_id is None:
            self._transport_controls.update_from_state(
                self._last_player_state,
                total_count=0,
                cursor_index=None,
                playing_index=None,
            )
            return
        cursor_index = None
        if self.cursor_item_id is not None:
            cursor_index = await self.store.get_item_index(
                self.playlist_id, self.cursor_item_id
            )
        playing_index = None
        if (
            self._last_player_state.status in {"playing", "paused"}
            and self._last_player_state.item_id is not None
        ):
            playing_index = await self.store.get_item_index(
                self.playlist_id, self._last_player_state.item_id
            )
        self._transport_controls.update_from_state(
            self._last_player_state,
            total_count=self.total_count,
            cursor_index=cursor_index,
            playing_index=playing_index,
        )

    async def refresh_view(self) -> None:
        if self.store is None or self.playlist_id is None:
            return
        await self._recompute_limit()
        try:
            self.total_count = await self.store.count(self.playlist_id)
            self.window_offset = self._clamp_offset(self.window_offset)
            self._rows = await self.store.fetch_window(
                self.playlist_id, self.window_offset, self.limit
            )
            if self.cursor_item_id is None and self._rows:
                self.cursor_item_id = self._rows[0].item_id
            self._update_viewport()
            await self._refresh_transport_controls()
            self._request_visible_metadata()
        except Exception as exc:  # pragma: no cover - UI safety net
            logger.exception("Failed to refresh playlist: %s", exc)
            await self._show_error("Failed to refresh playlist. See log file.")

    async def refresh_window(self) -> None:
        await self._refresh_window()

    async def refresh_visible_rows(self, updated_track_ids: set[int]) -> None:
        if self.store is None or self.playlist_id is None or not self._rows:
            return
        visible_track_ids = {row.track_id for row in self._rows}
        to_refresh = list(updated_track_ids.intersection(visible_track_ids))
        if not to_refresh:
            return
        try:
            fresh_rows = await self.store.fetch_rows_by_track_ids(
                self.playlist_id, to_refresh
            )
        except Exception as exc:  # pragma: no cover - UI safety net
            logger.exception("Failed to refresh playlist: %s", exc)
            await self._show_error("Failed to refresh playlist. See log file.")
            return
        if not fresh_rows:
            return
        row_index_map = {row.item_id: index for index, row in enumerate(self._rows)}
        for row in fresh_rows:
            index = row_index_map.get(row.item_id)
            if index is None:
                continue
            self._rows[index] = row
        self._update_viewport()

    async def _refresh_window(self) -> None:
        if self.store is None or self.playlist_id is None:
            return
        try:
            self._rows = await self.store.fetch_window(
                self.playlist_id, self.window_offset, self.limit
            )
            if self.cursor_item_id is None and self._rows:
                self.cursor_item_id = self._rows[0].item_id
            self._update_viewport()
            self._request_visible_metadata()
        except Exception as exc:  # pragma: no cover - UI safety net
            logger.exception("Failed to refresh playlist: %s", exc)
            await self._show_error("Failed to refresh playlist. See log file.")

    async def _recompute_limit(self) -> None:
        await asyncio.sleep(0)
        visible = max(1, self._viewport.size.height)
        self.limit = visible

    def _update_viewport(self) -> None:
        if DEBUG_VIEWPORT:
            cursor_in_rows = any(
                row.item_id == self.cursor_item_id for row in self._rows
            )
            logger.info(
                "viewport offset=%s limit=%s total=%s max_offset=%s cursor_in_rows=%s",
                self.window_offset,
                self.limit,
                self.total_count,
                self._max_offset(),
                cursor_in_rows,
            )
        self._viewport.update_model(
            rows=self._rows,
            total_count=self.total_count,
            offset=self.window_offset,
            limit=self.limit,
            cursor_item_id=self.cursor_item_id,
            selected_item_ids=self.selected_item_ids,
            playing_item_id=self.playing_item_id,
        )

    async def action_cursor_down(self) -> None:
        await self._move_cursor(1)

    async def action_cursor_up(self) -> None:
        await self._move_cursor(-1)

    async def action_play_selected(self) -> None:
        app = cast("TzPlayerApp", self.app)
        self.run_worker(app.action_play_selected(), exclusive=True)

    async def _move_cursor(self, delta: int) -> None:
        if not self._rows:
            return

        item_ids = [row.item_id for row in self._rows]

        # If cursor isn't in the current window, snap it sensibly
        if self.cursor_item_id not in item_ids:
            # Choose closest end based on direction of travel
            self.cursor_item_id = item_ids[-1] if delta > 0 else item_ids[0]
            self._update_viewport()
            await self._refresh_transport_controls()
            return

        idx = item_ids.index(self.cursor_item_id)
        next_idx = idx + delta

        # Move within current window
        if 0 <= next_idx < len(item_ids):
            self.cursor_item_id = item_ids[next_idx]
            self._update_viewport()
            await self._refresh_transport_controls()
            return

        # Need to scroll the window; preserve screen-row position
        new_offset = self._clamp_offset(self.window_offset + delta)
        if new_offset == self.window_offset:
            return

        self.window_offset = new_offset
        await self._refresh_window()

        # After refresh, keep cursor at same screen row (idx clamped)
        if self._rows:
            new_ids = [row.item_id for row in self._rows]
            pinned_idx = min(max(idx, 0), len(new_ids) - 1)
            self.cursor_item_id = new_ids[pinned_idx]
            self._update_viewport()
            await self._refresh_transport_controls()

    async def _scroll(self, delta: int) -> None:
        if self.total_count == 0:
            return
        new_offset = self._clamp_offset(self.window_offset + delta)
        if new_offset == self.window_offset:
            return
        self.window_offset = new_offset
        await self._refresh_window()

    def _max_offset(self) -> int:
        return max(0, self.total_count - self.limit)

    def _clamp_offset(self, value: int) -> int:
        return max(0, min(value, self._max_offset()))

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
                sorted(self.selected_item_ids),
                self.cursor_item_id,
            )
            await self.refresh_view()
        except Exception as exc:
            logger.exception("Failed to reorder: %s", exc)
            await self._show_error("Failed to reorder selection. See log file.")

    async def action_toggle_selection(self) -> None:
        if self.cursor_item_id is None:
            return
        if self.cursor_item_id in self.selected_item_ids:
            self.selected_item_ids.remove(self.cursor_item_id)
        else:
            self.selected_item_ids.add(self.cursor_item_id)
        self._update_viewport()
        self.post_message(self.SelectionChanged(len(self.selected_item_ids)))

    async def _handle_actions_menu(self, action: str) -> None:
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

    async def _open_actions_menu(self) -> None:
        if self._actions_popup is not None:
            self._actions_popup.dismiss()
            self._actions_popup = None
            return
        button = self.query_one("#playlist-actions", ActionsMenuButton)
        anchor = button.region
        popup = ActionsMenuPopup(anchor)
        self._actions_popup = popup
        await self.app.mount(popup)

    async def on_text_button_pressed(self, event: TextButtonPressed) -> None:
        if event.action == "reorder_up":
            await self._move_selection("up")
        elif event.action == "reorder_down":
            await self._move_selection("down")
        elif event.action == "actions_menu":
            await self._open_actions_menu()

    async def on_actions_menu_selected(self, event: ActionsMenuSelected) -> None:
        self._actions_popup = None
        await self._handle_actions_menu(event.action)
        self.focus()

    def on_actions_menu_dismissed(self, event: ActionsMenuDismissed) -> None:
        self._actions_popup = None
        self.focus()

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
        if not self.selected_item_ids:
            return
        confirmed = await self._confirm("Remove selected tracks?")
        if not confirmed:
            return
        await self._run_store_action(
            "remove selected", self.store.remove_items, self.selected_item_ids
        )
        self.selected_item_ids.clear()

    async def _clear_playlist(self) -> None:
        if self.store is None:
            return
        confirmed = await self._confirm("Clear the playlist?")
        if not confirmed:
            return
        await self._run_store_action("clear playlist", self.store.clear_playlist)
        self.selected_item_ids.clear()

    async def _refresh_metadata_selected(self) -> None:
        if self.store is None or self.playlist_id is None:
            return
        if not self.selected_item_ids:
            return
        try:
            logger.info("Playlist action: refresh metadata (selected)")
            track_ids = await asyncio.gather(
                *[
                    self.store.get_track_id_for_item(self.playlist_id, item_id)
                    for item_id in self.selected_item_ids
                ]
            )
            selected_track_ids = {track_id for track_id in track_ids if track_id}
            await self.store.invalidate_metadata(selected_track_ids)
            await self.refresh_view()
            self._metadata_pending.difference_update(selected_track_ids)
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
