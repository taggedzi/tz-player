"""Textual TUI app for tz-player."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Literal, cast

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.timer import Timer
from textual.widgets import Footer, Header, Static

from . import __version__
from .events import PlayerStateChanged, TrackChanged
from .logging_utils import setup_logging
from .paths import db_path, log_dir, state_path
from .runtime_config import resolve_log_level
from .services.fake_backend import FakePlaybackBackend
from .services.metadata_service import MetadataService
from .services.player_service import PlayerService, PlayerState, TrackInfo
from .services.playlist_store import PlaylistStore
from .services.vlc_backend import VLCPlaybackBackend
from .state_store import AppState, load_state, save_state
from .ui.actions_menu import ActionsMenuDismissed, ActionsMenuPopup, ActionsMenuSelected
from .ui.modals.error import ErrorModal
from .ui.playlist_pane import PlaylistPane
from .ui.status_pane import StatusPane
from .utils.async_utils import run_blocking
from .visualizers import (
    VisualizerContext,
    VisualizerFrameInput,
    VisualizerHost,
    VisualizerRegistry,
)

logger = logging.getLogger(__name__)
METADATA_REFRESH_DEBOUNCE = 0.2
SPEED_MIN = 0.5
SPEED_MAX = 4.0


class TzPlayerApp(App):
    TITLE = "tz-player"
    CSS = """
    Screen {
        layout: vertical;
    }

    #main {
        height: 1fr;
    }

    #playlist-pane {
        width: 1fr;
        min-width: 50%;
    }

    #playlist-top {
        height: 1;
        content-align: left middle;
    }

    #playlist-bottom {
        height: 2;
    }

    #playlist-actions {
        width: 12;
        height: 1;
        margin-right: 1;
        text-wrap: nowrap;
        overflow: hidden;
    }

    #reorder-up, #reorder-down {
        width: 2;
        height: 1;
        margin-right: 1;
    }

    #playlist-find {
        width: 1fr;
        height: 1;
        border: none;
        padding: 0 1;
        background: $panel;
        color: $text;
    }

    #playlist-find:focus {
        background: $boost;
        color: $text;
    }

    #playlist-viewport {
        height: 1fr;
        background: $panel;
    }

    #playlist-viewport:focus {
        background: $boost;
    }

    #right-pane {
        width: 1fr;
    }

    #visualizer-pane, #current-track-pane {
        border: solid white;
        height: 1fr;
        content-align: center middle;
    }

    #status-pane {
        height: 5;
        border: solid white;
        layout: vertical;
        padding: 0 1;
    }

    #status-line {
        height: 1;
    }

    ModalScreen {
        align: center middle;
    }

    #modal-body {
        padding: 1 2;
        border: solid white;
        width: 60%;
    }

    """
    BINDINGS = [
        ("escape", "dismiss_modal", "Dismiss"),
        ("space", "play_pause", "Play/Pause"),
        ("a", "open_actions_menu", "Actions"),
        ("f", "focus_find", "Find"),
        ("n", "next_track", "Next"),
        ("p", "previous_track", "Previous"),
        ("x", "stop", "Stop"),
        ("left", "seek_back", "Seek -5s"),
        ("right", "seek_forward", "Seek +5s"),
        ("shift+left", "seek_back_big", "Seek -30s"),
        ("shift+right", "seek_forward_big", "Seek +30s"),
        ("home", "seek_start", "Seek start"),
        ("end", "seek_end", "Seek end"),
        ("-", "volume_down", "Vol -"),
        ("+", "volume_up", "Vol +"),
        ("shift+-", "volume_down_big", "Vol -10"),
        ("shift+=", "volume_up_big", "Vol +10"),
        ("[", "speed_down", "Speed -"),
        ("]", "speed_up", "Speed +"),
        ("\\", "speed_reset", "Speed reset"),
        ("r", "repeat_mode", "Repeat"),
        ("s", "shuffle", "Shuffle"),
        ("z", "cycle_visualizer", "Visualizer"),
        ("q", "quit", "Quit"),
    ]

    def __init__(
        self, *, auto_init: bool = True, backend_name: str | None = None
    ) -> None:
        super().__init__()
        self.store = PlaylistStore(db_path())
        self.state = AppState()
        self.playlist_id: int | None = None
        self._auto_init = auto_init
        self._backend_name = backend_name
        self.player_service: PlayerService | None = None
        self.player_state = PlayerState()
        self.current_track: TrackInfo | None = None
        self.metadata_service: MetadataService | None = None
        self._metadata_refresh_task: asyncio.Task[None] | None = None
        self._metadata_pending_ids: set[int] = set()
        self._state_save_task: asyncio.Task[None] | None = None
        self._last_persisted: (
            tuple[int | None, int | None, int, float, str, bool] | None
        ) = None
        self.visualizer_registry: VisualizerRegistry | None = None
        self.visualizer_host: VisualizerHost | None = None
        self._visualizer_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Horizontal(
            PlaylistPane(id="playlist-pane"),
            Vertical(
                Static("Visualizer placeholder", id="visualizer-pane"),
                Static("Current track placeholder", id="current-track-pane"),
                id="right-pane",
            ),
            id="main",
        )
        yield StatusPane(id="status-pane")
        yield Footer()
        # Overlay layer removed due to layout conflicts with Textual 0.59

    def on_mount(self) -> None:
        if self._auto_init:
            asyncio.create_task(self._initialize_state())

    async def _initialize_state(self) -> None:
        try:
            self.state = await run_blocking(load_state, state_path())
            backend_name = _resolve_backend_name(
                self._backend_name, self.state.playback_backend
            )
            self.state = replace(self.state, playback_backend=backend_name)
            await run_blocking(save_state, state_path(), self.state)
            await self.store.initialize()
            playlist_id = await self.store.ensure_playlist("Default")
            if self.state.playlist_id != playlist_id:
                self.state = replace(self.state, playlist_id=playlist_id)
                await run_blocking(save_state, state_path(), self.state)
            self.playlist_id = playlist_id
            self.player_state = self._player_state_from_appstate(playlist_id)
            backend = _build_backend(backend_name)
            self.player_service = PlayerService(
                emit_event=self._handle_player_event,
                track_info_provider=self._track_info_provider,
                backend=backend,
                next_track_provider=self._next_track_provider,
                prev_track_provider=self._prev_track_provider,
                playlist_item_ids_provider=self._playlist_item_ids_provider,
                initial_state=self.player_state,
            )
            self.metadata_service = MetadataService(
                self.store, on_metadata_updated=self._handle_metadata_updated
            )
            try:
                await self.player_service.start()
            except Exception as exc:
                logger.exception("Failed to start backend %s: %s", backend_name, exc)
                if backend_name != "fake":
                    backend_name = "fake"
                    self.state = replace(self.state, playback_backend=backend_name)
                    await run_blocking(save_state, state_path(), self.state)
                    backend = _build_backend(backend_name)
                    self.player_service = PlayerService(
                        emit_event=self._handle_player_event,
                        track_info_provider=self._track_info_provider,
                        backend=backend,
                        next_track_provider=self._next_track_provider,
                        prev_track_provider=self._prev_track_provider,
                        playlist_item_ids_provider=self._playlist_item_ids_provider,
                        initial_state=self.player_state,
                    )
                    await self.player_service.start()
                    await self.push_screen(
                        ErrorModal(
                            "VLC backend unavailable; using fake backend.\n"
                            "Cause: VLC/libVLC runtime is not available.\n"
                            "Next step: install VLC/libVLC, then restart to use --backend vlc."
                        )
                    )
                else:
                    raise
            self.query_one(StatusPane).set_player_service(self.player_service)
            self._last_persisted = self._state_tuple(self.player_state)
            pane = self.query_one(PlaylistPane)
            await pane.configure(
                self.store,
                playlist_id,
                self.state.current_item_id,
                self.metadata_service,
            )
            pane.focus()
            self._update_status_pane()
            await pane.update_transport_controls(self.player_state)
            self._update_current_track_pane()
            await self._start_visualizer()
        except Exception as exc:
            logger.exception("Failed to initialize app: %s", exc)
            await self.push_screen(
                ErrorModal(
                    "Failed to initialize app.\n"
                    "Likely cause: state/database/backend startup failure.\n"
                    "Next step: verify file permissions/paths and review the log file."
                )
            )

    async def on_unmount(self) -> None:
        self._stop_visualizer()
        if self.player_service is not None:
            await self.player_service.shutdown()

    def action_dismiss_modal(self) -> None:
        if isinstance(self.screen, ModalScreen):
            self.pop_screen()
            return
        popup = self.query(ActionsMenuPopup)
        if popup:
            popup.first().dismiss()
            return
        pane = self.query_one(PlaylistPane)
        if pane.is_find_focused() or pane.has_find_text():
            pane.clear_find_and_focus()

    def action_focus_find(self) -> None:
        self.query_one(PlaylistPane).focus_find()

    async def action_open_actions_menu(self) -> None:
        pane = self.query_one(PlaylistPane)
        await pane._open_actions_menu()

    async def action_play_pause(self) -> None:
        if self.player_service is None or self.playlist_id is None:
            return
        if (
            self.player_state.status in {"idle", "stopped"}
            or self.player_state.item_id is None
        ):
            cursor_id = self.query_one(PlaylistPane).get_cursor_item_id()
            if cursor_id is None:
                return
            await self.player_service.play_item(self.playlist_id, cursor_id)
            return
        await self.player_service.toggle_pause()

    def on_mouse_down(self, event) -> None:
        popup = self.query(ActionsMenuPopup)
        if not popup:
            return
        menu = popup.first()
        if not menu.contains_point(event.screen_x, event.screen_y):
            menu.dismiss()
            event.stop()

    def on_key(self, event) -> None:
        if event.key != "escape":
            return
        popup = self.query(ActionsMenuPopup)
        if not popup:
            return
        popup.first().dismiss()
        event.stop()

    async def on_actions_menu_selected(self, event: ActionsMenuSelected) -> None:
        logger.debug("ActionsMenuSelected: action=%s", event.action)
        pane = self.query_one(PlaylistPane)
        pane._actions_popup = None
        await pane._handle_actions_menu(event.action)
        pane.focus()

    def on_actions_menu_dismissed(self, event: ActionsMenuDismissed) -> None:
        pane = self.query_one(PlaylistPane)
        pane._actions_popup = None
        pane.focus()

    async def action_play_selected(self) -> None:
        if self.player_service is None or self.playlist_id is None:
            return
        cursor_id = self.query_one(PlaylistPane).get_cursor_item_id()
        if cursor_id is None:
            return
        await self.player_service.play_item(self.playlist_id, cursor_id)

    async def action_quit(self) -> None:
        self.exit()

    async def action_stop(self) -> None:
        if self.player_service is None:
            return
        await self.player_service.stop()

    async def action_next_track(self) -> None:
        if self.player_service is None:
            return
        await self.player_service.next_track()

    async def action_previous_track(self) -> None:
        if self.player_service is None:
            return
        await self.player_service.previous_track()

    async def action_seek_back(self) -> None:
        if self.player_service is None:
            return
        await self.player_service.seek_delta_ms(-5000)

    async def action_seek_forward(self) -> None:
        if self.player_service is None:
            return
        await self.player_service.seek_delta_ms(5000)

    async def action_seek_back_big(self) -> None:
        if self.player_service is None:
            return
        await self.player_service.seek_delta_ms(-30000)

    async def action_seek_forward_big(self) -> None:
        if self.player_service is None:
            return
        await self.player_service.seek_delta_ms(30000)

    async def action_seek_start(self) -> None:
        if self.player_service is None:
            return
        await self.player_service.seek_ratio(0.0)

    async def action_seek_end(self) -> None:
        if self.player_service is None:
            return
        await self.player_service.seek_ratio(1.0)

    async def action_volume_down(self) -> None:
        if self.player_service is None:
            return
        await self.player_service.set_volume(self.player_state.volume - 5)

    async def action_volume_up(self) -> None:
        if self.player_service is None:
            return
        await self.player_service.set_volume(self.player_state.volume + 5)

    async def action_volume_down_big(self) -> None:
        if self.player_service is None:
            return
        await self.player_service.set_volume(self.player_state.volume - 10)

    async def action_volume_up_big(self) -> None:
        if self.player_service is None:
            return
        await self.player_service.set_volume(self.player_state.volume + 10)

    async def action_speed_down(self) -> None:
        if self.player_service is None:
            return
        await self.player_service.change_speed(-1)

    async def action_speed_up(self) -> None:
        if self.player_service is None:
            return
        await self.player_service.change_speed(1)

    async def action_speed_reset(self) -> None:
        if self.player_service is None:
            return
        await self.player_service.reset_speed()

    async def action_repeat_mode(self) -> None:
        if self.player_service is None:
            return
        await self.player_service.cycle_repeat_mode()

    async def action_shuffle(self) -> None:
        if self.player_service is None:
            return
        anchor_id = None
        if self.player_state.item_id is None:
            anchor_id = self.query_one(PlaylistPane).get_cursor_item_id()
        await self.player_service.toggle_shuffle(anchor_item_id=anchor_id)

    async def action_cycle_visualizer(self) -> None:
        if self.visualizer_registry is None or self.visualizer_host is None:
            return
        plugin_ids = self.visualizer_registry.plugin_ids()
        if not plugin_ids:
            return
        try:
            current_idx = plugin_ids.index(self.visualizer_host.active_id)
        except ValueError:
            current_idx = 0
        next_idx = (current_idx + 1) % len(plugin_ids)
        next_id = plugin_ids[next_idx]
        context = VisualizerContext(
            ansi_enabled=self.state.ansi_enabled,
            unicode_enabled=True,
        )
        try:
            active = self.visualizer_host.activate(next_id, context)
        except Exception as exc:
            logger.exception("Failed to switch visualizer to '%s': %s", next_id, exc)
            await self.push_screen(
                ErrorModal("Failed to switch visualizer. See log file.")
            )
            return
        self.state = replace(self.state, visualizer_id=active)
        await run_blocking(save_state, state_path(), self.state)
        self._render_visualizer_frame()

    async def handle_playlist_cleared(self) -> None:
        if self.player_service is not None:
            await self.player_service.stop()
        self.current_track = None
        self._update_current_track_pane()
        if self._metadata_refresh_task is not None:
            self._metadata_refresh_task.cancel()
            self._metadata_refresh_task = None
        self._metadata_pending_ids.clear()

    async def _handle_player_event(self, event: object) -> None:
        if isinstance(event, PlayerStateChanged):
            self.player_state = event.state
            playing_id = (
                event.state.item_id
                if event.state.status in {"playing", "paused"}
                else None
            )
            pane = self.query_one(PlaylistPane)
            pane.set_playing_item_id(playing_id)
            self._update_status_pane()
            await pane.update_transport_controls(self.player_state)
            if self._state_tuple(self.player_state) != self._last_persisted:
                await self._schedule_state_save()
        elif isinstance(event, TrackChanged):
            self.current_track = event.track_info
            self._update_current_track_pane()
            item_id = self.player_state.item_id
            if (
                item_id is not None
                and self.current_track is not None
                and _track_needs_metadata(self.current_track)
                and self.metadata_service is not None
            ):
                track_id = await self.store.get_track_id_for_item(
                    self.playlist_id or 0, item_id
                )
                if track_id is not None:
                    self.run_worker(
                        self.metadata_service.ensure_metadata([track_id]),
                        exclusive=False,
                    )

    async def _track_info_provider(
        self, playlist_id: int, item_id: int
    ) -> TrackInfo | None:
        row = await self.store.get_item_row(playlist_id, item_id)
        if row is None:
            return None
        if not row.meta_valid:
            return TrackInfo(
                title=None,
                artist=None,
                album=None,
                year=None,
                path=str(row.path),
                duration_ms=None,
            )
        return TrackInfo(
            title=row.title,
            artist=row.artist,
            album=row.album,
            year=row.year,
            path=str(row.path),
            duration_ms=row.duration_ms,
        )

    async def _next_track_provider(
        self, playlist_id: int, item_id: int, wrap: bool
    ) -> int | None:
        return await self.store.get_next_item_id(playlist_id, item_id, wrap=wrap)

    async def _prev_track_provider(
        self, playlist_id: int, item_id: int, wrap: bool
    ) -> int | None:
        return await self.store.get_prev_item_id(playlist_id, item_id, wrap=wrap)

    async def _playlist_item_ids_provider(self, playlist_id: int) -> list[int]:
        return await self.store.list_item_ids(playlist_id)

    def _update_status_pane(self) -> None:
        self.query_one(StatusPane).update_state(self.player_state)

    def _update_current_track_pane(self) -> None:
        pane = self.query_one("#current-track-pane", Static)
        if self.current_track is None:
            pane.update("No track selected")
            return
        title = self.current_track.title or Path(self.current_track.path).name
        artist = self.current_track.artist or "Unknown artist"
        album = self.current_track.album or "Unknown album"
        duration = _format_time(self.current_track.duration_ms or 0)
        pane.update(f"{title}\n{artist}\n{album}\n{duration}")

    async def _start_visualizer(self) -> None:
        self.visualizer_registry = VisualizerRegistry.built_in()
        self.visualizer_host = VisualizerHost(self.visualizer_registry, target_fps=10)
        context = VisualizerContext(
            ansi_enabled=self.state.ansi_enabled,
            unicode_enabled=True,
        )
        requested = self.state.visualizer_id or self.visualizer_registry.default_id
        active = self.visualizer_host.activate(requested, context)
        if self.state.visualizer_id != active:
            self.state = replace(self.state, visualizer_id=active)
            await run_blocking(save_state, state_path(), self.state)
        self._render_visualizer_frame()
        interval = 1.0 / self.visualizer_host.target_fps
        self._visualizer_timer = self.set_interval(
            interval, self._render_visualizer_frame
        )

    def _stop_visualizer(self) -> None:
        if self._visualizer_timer is not None:
            self._visualizer_timer.stop()
            self._visualizer_timer = None
        if self.visualizer_host is not None:
            self.visualizer_host.shutdown()
            self.visualizer_host = None

    def _render_visualizer_frame(self) -> None:
        if self.visualizer_host is None:
            return
        pane = self.query_one("#visualizer-pane", Static)
        context = VisualizerContext(
            ansi_enabled=self.state.ansi_enabled,
            unicode_enabled=True,
        )
        frame = VisualizerFrameInput(
            frame_index=self.visualizer_host.frame_index,
            monotonic_s=time.monotonic(),
            width=max(1, pane.size.width),
            height=max(1, pane.size.height),
            status=self.player_state.status,
            position_s=max(0.0, self.player_state.position_ms / 1000.0),
            duration_s=self.player_state.duration_ms / 1000.0
            if self.player_state.duration_ms > 0
            else None,
            volume=float(self.player_state.volume),
            speed=self.player_state.speed,
            repeat_mode=self.player_state.repeat_mode,
            shuffle=self.player_state.shuffle,
            track_id=None,
            track_path=self.current_track.path
            if self.current_track is not None
            else None,
            title=self.current_track.title if self.current_track is not None else None,
            artist=self.current_track.artist
            if self.current_track is not None
            else None,
            album=self.current_track.album if self.current_track is not None else None,
        )
        try:
            output = self.visualizer_host.render_frame(frame, context)
        except Exception as exc:  # pragma: no cover - UI safety net
            logger.exception("Visualizer host render failed: %s", exc)
            pane.update("Visualizer unavailable")
            return
        notice = self.visualizer_host.consume_notice()
        pane.update(f"{notice}\n{output}" if notice else output)

    async def _handle_metadata_updated(self, track_ids: list[int]) -> None:
        pane = self.query_one(PlaylistPane)
        pane.mark_metadata_done(track_ids)
        self._metadata_pending_ids.update(track_ids)
        if self._metadata_refresh_task is None:
            self._metadata_refresh_task = asyncio.create_task(
                self._refresh_metadata_debounced()
            )
        if self.player_state.item_id is not None:
            current_track_id = await self.store.get_track_id_for_item(
                self.playlist_id or 0, self.player_state.item_id
            )
            if current_track_id in track_ids:
                await self._refresh_current_track_info()

    async def _refresh_current_track_info(self) -> None:
        if self.playlist_id is None or self.player_state.item_id is None:
            return
        self.current_track = await self._track_info_provider(
            self.playlist_id, self.player_state.item_id
        )
        self._update_current_track_pane()

    async def _refresh_metadata_debounced(self) -> None:
        try:
            await asyncio.sleep(METADATA_REFRESH_DEBOUNCE)
            pane = self.query_one(PlaylistPane)
            to_process = set(self._metadata_pending_ids)
            if to_process:
                await pane.refresh_visible_rows(to_process)
                self._metadata_pending_ids.difference_update(to_process)
        finally:
            self._metadata_refresh_task = None
            if self._metadata_pending_ids:
                self._metadata_refresh_task = asyncio.create_task(
                    self._refresh_metadata_debounced()
                )

    def _player_state_from_appstate(self, playlist_id: int) -> PlayerState:
        repeat_mode = _repeat_from_state(self.state.repeat_mode)
        volume = self.state.volume
        speed = _clamp_speed(self.state.speed)
        if volume <= 1.0:
            volume = volume * 100
        return PlayerState(
            playlist_id=playlist_id,
            item_id=self.state.current_item_id,
            volume=int(volume),
            speed=speed,
            repeat_mode=repeat_mode,
            shuffle=self.state.shuffle,
        )

    async def _schedule_state_save(self) -> None:
        if self._state_save_task is not None:
            self._state_save_task.cancel()
        self._state_save_task = asyncio.create_task(self._save_state_debounced())

    async def _save_state_debounced(self) -> None:
        try:
            await asyncio.sleep(1.0)
            self.state = replace(
                self.state,
                playlist_id=self.player_state.playlist_id,
                current_item_id=self.player_state.item_id,
                volume=float(self.player_state.volume),
                speed=self.player_state.speed,
                repeat_mode=self.player_state.repeat_mode.lower(),
                shuffle=self.player_state.shuffle,
                playback_backend=self.state.playback_backend,
            )
            self._last_persisted = self._state_tuple(self.player_state)
            await run_blocking(save_state, state_path(), self.state)
        except asyncio.CancelledError:
            return

    def _state_tuple(
        self, state: PlayerState
    ) -> tuple[int | None, int | None, int, float, str, bool]:
        return (
            state.playlist_id,
            state.item_id,
            state.volume,
            state.speed,
            state.repeat_mode,
            state.shuffle,
        )


def _format_time(position_ms: int) -> str:
    if position_ms <= 0:
        return "--:--"
    seconds = position_ms // 1000
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


def _repeat_from_state(value: str) -> Literal["OFF", "ONE", "ALL"]:
    value = value.upper()
    if value in {"OFF", "ONE", "ALL"}:
        return cast(Literal["OFF", "ONE", "ALL"], value)
    return "OFF"


def _track_needs_metadata(track: TrackInfo) -> bool:
    return (
        track.title is None
        or track.artist is None
        or track.album is None
        or track.duration_ms is None
    )


def _clamp_speed(speed: float) -> float:
    return max(SPEED_MIN, min(speed, SPEED_MAX))


def _resolve_backend_name(cli_backend: str | None, state_backend: str | None) -> str:
    if cli_backend in {"fake", "vlc"}:
        return cli_backend
    if state_backend in {"fake", "vlc"}:
        return state_backend
    return "fake"


def _build_backend(name: str) -> FakePlaybackBackend | VLCPlaybackBackend:
    logger.info("Playback backend selected: %s", name)
    if name == "vlc":
        return VLCPlaybackBackend()
    return FakePlaybackBackend()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tz-player", description="TaggedZ's command line music player."
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument(
        "--quiet", action="store_true", help="Only show warnings and errors"
    )
    parser.add_argument("--log-file", help="Write logs to a file path")
    parser.add_argument(
        "--backend",
        choices=("fake", "vlc"),
        help="Playback backend to use (fake or vlc).",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        level = resolve_log_level(verbose=args.verbose, quiet=args.quiet)
        setup_logging(
            log_dir=log_dir(),
            level=level,
            log_file=Path(args.log_file) if args.log_file else None,
        )
        logging.getLogger(__name__).info("Starting tz-player TUI")
        TzPlayerApp(backend_name=args.backend).run()
        return 0
    except Exception as exc:  # pragma: no cover - top-level safety net
        logging.getLogger(__name__).exception("Fatal startup error: %s", exc)
        print(
            "Startup failed. Verify backend/state/log paths and re-run with --verbose.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
