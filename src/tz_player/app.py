"""Textual TUI app for tz-player."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sqlite3
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Callable, Literal, cast

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.theme import Theme
from textual.timer import Timer
from textual.widgets import Footer, Header, Static

from . import __version__
from .doctor import render_report, run_doctor
from .events import PlayerStateChanged, TrackChanged
from .logging_utils import setup_logging
from .paths import db_path, log_dir, state_path
from .runtime_config import resolve_log_level
from .services.audio_envelope_analysis import (
    analyze_track_envelope,
    ffmpeg_available,
    requires_ffmpeg_for_envelope,
)
from .services.audio_envelope_store import SqliteEnvelopeStore
from .services.audio_tags import read_audio_tags
from .services.fake_backend import FakePlaybackBackend
from .services.metadata_service import MetadataService
from .services.player_service import PlayerService, PlayerState, TrackInfo
from .services.playlist_store import PlaylistStore
from .services.vlc_backend import VLCPlaybackBackend
from .state_store import AppState, load_state_with_notice, save_state
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
CYBERPUNK_THEME = Theme(
    name="cyberpunk-clean",
    primary="#00D7E6",
    secondary="#00B8C4",
    warning="#FF5A36",
    error="#FF3B3B",
    success="#35E68A",
    accent="#F2C94C",
    foreground="#C7D0D9",
    background="#0B0F14",
    surface="#111923",
    panel="#0F1621",
    boost="#16202D",
    dark=True,
)


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

    #visualizer-pane {
        border: solid $secondary;
        height: 1fr;
        content-align: center middle;
    }

    #current-track-pane {
        border: solid $secondary;
        height: 6;
        content-align: left top;
        padding: 0 1;
    }

    #status-pane {
        height: 5;
        border: solid $secondary;
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
        border: solid $secondary;
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
        self,
        *,
        auto_init: bool = True,
        backend_name: str | None = None,
        visualizer_fps_override: int | None = None,
        visualizer_plugin_paths_override: list[str] | None = None,
    ) -> None:
        super().__init__()
        self.register_theme(CYBERPUNK_THEME)
        self.theme = CYBERPUNK_THEME.name
        self.store = PlaylistStore(db_path())
        self.state = AppState()
        self.playlist_id: int | None = None
        self._auto_init = auto_init
        self._backend_name = backend_name
        self._visualizer_fps_override = visualizer_fps_override
        self._visualizer_plugin_paths_override = visualizer_plugin_paths_override
        self.player_service: PlayerService | None = None
        self.player_state = PlayerState()
        self.current_track: TrackInfo | None = None
        self.metadata_service: MetadataService | None = None
        self.audio_envelope_store: SqliteEnvelopeStore | None = None
        self._metadata_refresh_task: asyncio.Task[None] | None = None
        self._metadata_pending_ids: set[int] = set()
        self._envelope_analysis_tasks: dict[str, asyncio.Task[None]] = {}
        self._next_prewarm_task: asyncio.Task[None] | None = None
        self._next_prewarm_context: tuple[int, int, str, bool, int] | None = None
        self._envelope_missing_ffmpeg_warned: set[str] = set()
        self._audio_level_notice: str | None = None
        self._runtime_notice: str | None = None
        self._runtime_notice_expiry_s: float | None = None
        self._state_save_task: asyncio.Task[None] | None = None
        self._last_persisted: (
            tuple[int | None, int | None, int, float, str, bool] | None
        ) = None
        self.visualizer_registry: VisualizerRegistry | None = None
        self.visualizer_host: VisualizerHost | None = None
        self._visualizer_timer: Timer | None = None
        self.startup_failed = False

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
            self.state, state_notice = await run_blocking(
                load_state_with_notice, state_path()
            )
            backend_name = _resolve_backend_name(
                self._backend_name, self.state.playback_backend
            )
            state_fps = _normalize_persisted_visualizer_fps(self.state.visualizer_fps)
            effective_fps = (
                _clamp_int(self._visualizer_fps_override, 2, 30)
                if self._visualizer_fps_override is not None
                else state_fps
            )
            self.state = replace(
                self.state,
                playback_backend=backend_name,
                visualizer_fps=effective_fps,
                visualizer_plugin_paths=tuple(self._visualizer_plugin_paths_override)
                if self._visualizer_plugin_paths_override is not None
                else self.state.visualizer_plugin_paths,
            )
            await run_blocking(save_state, state_path(), self.state)
            try:
                await self.store.initialize()
                self.audio_envelope_store = SqliteEnvelopeStore(db_path())
                await self.audio_envelope_store.initialize()
                playlist_id = await self.store.ensure_playlist("Default")
            except Exception as exc:
                raise RuntimeError("Database startup failed") from exc
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
                envelope_provider=self.audio_envelope_store,
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
                        envelope_provider=self.audio_envelope_store,
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
            if state_notice is not None:
                await self.push_screen(ErrorModal(state_notice))
        except Exception as exc:
            logger.exception("Failed to initialize app: %s", exc)
            self.startup_failed = True
            await self.push_screen(ErrorModal(_startup_failure_message(exc, db_path())))

    async def on_unmount(self) -> None:
        self._stop_visualizer()
        for task in self._envelope_analysis_tasks.values():
            task.cancel()
        if self._envelope_analysis_tasks:
            await asyncio.gather(
                *self._envelope_analysis_tasks.values(), return_exceptions=True
            )
            self._envelope_analysis_tasks.clear()
        self._cancel_next_track_prewarm()
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
                ErrorModal(
                    "Failed to switch visualizer.\n"
                    "Likely cause: selected plugin failed during activation/render.\n"
                    "Next step: choose another visualizer and review the log file."
                )
            )
            return
        self.state = replace(self.state, visualizer_id=active)
        await run_blocking(save_state, state_path(), self.state)
        self._render_visualizer_frame()

    async def handle_playlist_cleared(self) -> None:
        self._cancel_next_track_prewarm()
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
            if event.state.error:
                self._set_runtime_notice(event.state.error, ttl_s=8.0)
            self._schedule_next_track_prewarm()
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
            if event.track_info is not None:
                self._schedule_envelope_analysis(event.track_info)
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

    def _schedule_envelope_analysis(self, track: TrackInfo) -> None:
        if self.audio_envelope_store is None:
            return
        key = track.path
        if not key:
            return
        self._update_audio_level_notice(key)
        existing = self._envelope_analysis_tasks.get(key)
        if existing is not None and not existing.done():
            return
        task = asyncio.create_task(self._ensure_envelope_for_track(track))
        self._envelope_analysis_tasks[key] = task
        task.add_done_callback(self._make_envelope_task_cleanup(key))

    def _schedule_next_track_prewarm(self, *, force: bool = False) -> None:
        if self.player_service is None or self.audio_envelope_store is None:
            self._cancel_next_track_prewarm()
            return
        state = self.player_state
        if (
            state.status != "playing"
            or state.playlist_id is None
            or state.item_id is None
        ):
            self._cancel_next_track_prewarm()
            return
        context = (
            state.playlist_id,
            state.item_id,
            state.repeat_mode,
            state.shuffle,
            state.position_ms // 5000,
        )
        if not force and self._next_prewarm_context == context:
            if self._next_prewarm_task is None or self._next_prewarm_task.done():
                # Context already warmed; avoid repeated prewarm churn on frequent state emits.
                return
            return
        self._cancel_next_track_prewarm()
        self._next_prewarm_context = context
        self._next_prewarm_task = asyncio.create_task(
            self._run_next_track_prewarm(context)
        )

    def _cancel_next_track_prewarm(self) -> None:
        if self._next_prewarm_task is not None:
            self._next_prewarm_task.cancel()
            self._next_prewarm_task = None
        self._next_prewarm_context = None

    async def _run_next_track_prewarm(
        self, context: tuple[int, int, str, bool, int]
    ) -> None:
        try:
            await asyncio.sleep(0.2)
            if self._next_prewarm_context != context:
                return
            if self.player_service is None:
                return
            next_item_id = await self.player_service.predict_next_item_id()
            if next_item_id is None:
                return
            playlist_id = self.player_state.playlist_id
            if playlist_id is None:
                return
            row = await self.store.get_item_row(playlist_id, next_item_id)
            if row is None:
                return
            await self._ensure_envelope_for_track(
                TrackInfo(
                    title=row.title,
                    artist=row.artist,
                    album=row.album,
                    year=row.year,
                    path=str(row.path),
                    duration_ms=row.duration_ms,
                )
            )
        except asyncio.CancelledError:
            return
        finally:
            if self._next_prewarm_context == context:
                self._next_prewarm_task = None

    def _make_envelope_task_cleanup(
        self, path_key: str
    ) -> Callable[[asyncio.Task[None]], None]:
        def _cleanup(_task: asyncio.Task[None]) -> None:
            self._envelope_analysis_tasks.pop(path_key, None)

        return _cleanup

    async def _ensure_envelope_for_track(self, track: TrackInfo) -> None:
        if self.audio_envelope_store is None:
            return
        path = Path(track.path)
        try:
            if await self.audio_envelope_store.has_envelope(path):
                logger.debug("Envelope cache hit for %s", path)
                self._update_audio_level_notice(str(path))
                return
            logger.debug("Envelope cache miss for %s; starting analysis.", path)
            result = await run_blocking(analyze_track_envelope, path)
            if result is None or not result.points:
                if requires_ffmpeg_for_envelope(path) and not ffmpeg_available():
                    path_key = str(path)
                    if path_key not in self._envelope_missing_ffmpeg_warned:
                        self._envelope_missing_ffmpeg_warned.add(path_key)
                        logger.warning(
                            "Envelope analysis unavailable for %s: ffmpeg not found on PATH; using fallback levels.",
                            path,
                        )
                        self._set_runtime_notice(
                            "ffmpeg not found; using fallback audio levels.",
                            ttl_s=10.0,
                        )
                    self._update_audio_level_notice(path_key)
                else:
                    logger.debug("Envelope analysis unavailable for %s", path)
                return
            await self.audio_envelope_store.upsert_envelope(
                path,
                result.points,
                duration_ms=max(1, result.duration_ms),
            )
            logger.info(
                "Envelope analyzed for %s (%d points)", path, len(result.points)
            )
            self._update_audio_level_notice(str(path))
        except Exception as exc:
            logger.warning("Envelope analysis failed for %s: %s", path, exc)
            self._set_runtime_notice(
                "Envelope analysis failed; using fallback audio levels.",
                ttl_s=10.0,
            )

    async def _track_info_provider(
        self, playlist_id: int, item_id: int
    ) -> TrackInfo | None:
        row = await self.store.get_item_row(playlist_id, item_id)
        if row is None:
            return None
        genre, bitrate_kbps = await run_blocking(_read_track_extras, row.path)
        if not row.meta_valid:
            return TrackInfo(
                title=None,
                artist=None,
                album=None,
                year=None,
                path=str(row.path),
                duration_ms=None,
                genre=genre,
                bitrate_kbps=bitrate_kbps,
            )
        return TrackInfo(
            title=row.title,
            artist=row.artist,
            album=row.album,
            year=row.year,
            path=str(row.path),
            duration_ms=row.duration_ms,
            genre=genre,
            bitrate_kbps=bitrate_kbps,
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
        pane = self.query_one(StatusPane)
        pane.set_runtime_notice(self._effective_runtime_notice())
        pane.update_state(self.player_state)

    def _update_current_track_pane(self) -> None:
        pane = self.query_one("#current-track-pane", Static)
        pane.update(_format_track_info_panel(self.current_track))

    async def _start_visualizer(self) -> None:
        local_plugin_paths = list(self.state.visualizer_plugin_paths)
        if local_plugin_paths:
            self.visualizer_registry = VisualizerRegistry.built_in(
                local_plugin_paths=local_plugin_paths
            )
        else:
            self.visualizer_registry = VisualizerRegistry.built_in()
        self.visualizer_host = VisualizerHost(
            self.visualizer_registry, target_fps=self.state.visualizer_fps
        )
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
            level_left=self.player_state.level_left,
            level_right=self.player_state.level_right,
            level_source=self.player_state.level_source,
        )
        try:
            output = self.visualizer_host.render_frame(frame, context)
        except Exception as exc:  # pragma: no cover - UI safety net
            logger.exception("Visualizer host render failed: %s", exc)
            pane.update("Visualizer unavailable")
            return
        notice = self.visualizer_host.consume_notice()
        if notice:
            self._set_runtime_notice(notice, ttl_s=8.0)
        audio_notice = self._audio_level_notice
        if notice and audio_notice:
            render_text = f"{notice}\n{audio_notice}\n{output}"
        elif notice:
            render_text = f"{notice}\n{output}"
        elif audio_notice:
            render_text = f"{audio_notice}\n{output}"
        else:
            render_text = output
        pane.update(Text.from_ansi(render_text))

    def _update_audio_level_notice(self, track_path: str) -> None:
        if self.current_track is None:
            self._audio_level_notice = None
            return
        if self.current_track.path != track_path:
            return
        if self.player_state.level_source == "envelope":
            self._audio_level_notice = None
            return
        if requires_ffmpeg_for_envelope(track_path) and not ffmpeg_available():
            self._audio_level_notice = "DIAG: ffmpeg missing; envelope cache unavailable for this track (using fallback levels)."
            self._set_runtime_notice(
                "ffmpeg missing for envelope analysis; using fallback levels.",
                ttl_s=10.0,
            )
            return
        self._audio_level_notice = None

    def _set_runtime_notice(self, message: str, *, ttl_s: float = 8.0) -> None:
        text = message.strip()
        if not text:
            return
        self._runtime_notice = text
        self._runtime_notice_expiry_s = time.monotonic() + max(1.0, ttl_s)

    def _effective_runtime_notice(self) -> str | None:
        if self._runtime_notice is None:
            return None
        expires = self._runtime_notice_expiry_s
        if expires is not None and time.monotonic() >= expires:
            self._runtime_notice = None
            self._runtime_notice_expiry_s = None
            return None
        return self._runtime_notice

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


def _format_track_info_panel(track: TrackInfo | None) -> Text:
    if track is None:
        title = "--"
        artist = "--"
        genre = None
        album = "--"
        year_text = "----"
        duration = "--:--"
        bitrate_text = "--"
    else:
        title = track.title or Path(track.path).name
        artist = track.artist or "Unknown"
        genre = track.genre
        album = track.album or "Unknown"
        year_text = str(track.year) if track.year is not None else "----"
        duration = _format_time(track.duration_ms or 0)
        bitrate_text = (
            f"{track.bitrate_kbps} kbps" if track.bitrate_kbps is not None else "--"
        )

    label_style = "bold #F2C94C"
    text = Text()
    text.append("Title: ", style=label_style)
    text.append(title)
    text.append("\n")
    text.append("Artist: ", style=label_style)
    text.append(artist)
    if genre:
        text.append(" | ")
        text.append("Genre: ", style=label_style)
        text.append(genre)
    text.append("\n")
    text.append("Album: ", style=label_style)
    text.append(album)
    text.append(" | ")
    text.append("Year: ", style=label_style)
    text.append(year_text)
    text.append("\n")
    text.append("Time: ", style=label_style)
    text.append(duration)
    text.append(" | ")
    text.append("Bitrate: ", style=label_style)
    text.append(bitrate_text)
    return text


def _read_track_extras(path: Path) -> tuple[str | None, int | None]:
    tags = read_audio_tags(path)
    return tags.genre, tags.bitrate_kbps


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


def _normalize_persisted_visualizer_fps(value: int) -> int:
    if 2 <= value <= 30:
        return value
    return 10


def _clamp_int(value: int, min_value: int, max_value: int) -> int:
    return max(min_value, min(value, max_value))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tz-player", description="TaggedZ's command line music player."
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=("run", "doctor"),
        default="run",
        help="Run player UI (default) or print environment diagnostics.",
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
    parser.add_argument(
        "--visualizer-fps",
        type=int,
        help="Visualizer render cadence (clamped to 2-30 FPS).",
    )
    parser.add_argument(
        "--visualizer-plugin-path",
        action="append",
        dest="visualizer_plugin_paths",
        help="Local visualizer module/package path (repeatable).",
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
            console=False,
        )
        if getattr(args, "command", "run") == "doctor":
            report = run_doctor(args.backend or "fake")
            print(render_report(report))
            return report.exit_code
        logging.getLogger(__name__).info("Starting tz-player TUI")
        visualizer_fps = getattr(args, "visualizer_fps", None)
        visualizer_plugin_paths = getattr(args, "visualizer_plugin_paths", None)
        if visualizer_fps is not None and visualizer_plugin_paths is not None:
            app = TzPlayerApp(
                backend_name=args.backend,
                visualizer_fps_override=visualizer_fps,
                visualizer_plugin_paths_override=visualizer_plugin_paths,
            )
        elif visualizer_fps is not None:
            app = TzPlayerApp(
                backend_name=args.backend,
                visualizer_fps_override=visualizer_fps,
            )
        elif visualizer_plugin_paths is not None:
            app = TzPlayerApp(
                backend_name=args.backend,
                visualizer_plugin_paths_override=visualizer_plugin_paths,
            )
        else:
            app = TzPlayerApp(backend_name=args.backend)
        app.run()
        return 1 if getattr(app, "startup_failed", False) else 0
    except Exception as exc:  # pragma: no cover - top-level safety net
        logging.getLogger(__name__).exception("Fatal startup error: %s", exc)
        print(
            "Startup failed. Verify backend/state/log paths and re-run with --verbose.",
            file=sys.stderr,
        )
        return 1


def _startup_failure_message(exc: Exception, db_file: Path) -> str:
    db_failure_message = _classify_db_startup_failure(exc, db_file)
    if db_failure_message is not None:
        return db_failure_message
    return (
        "Failed to initialize app.\n"
        "Likely cause: state/database/backend startup failure.\n"
        "Next step: verify file permissions/paths and review the log file."
    )


def _classify_db_startup_failure(exc: Exception, db_file: Path) -> str | None:
    chain: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and current not in chain:
        chain.append(current)
        current = current.__cause__
    db_context = any(
        isinstance(item, sqlite3.Error)
        or "database startup failed" in str(item).lower()
        for item in chain
    )
    if not db_context:
        return None
    root: BaseException = chain[-1]
    for item in reversed(chain):
        if isinstance(item, (sqlite3.Error, OSError, PermissionError)):
            root = item
            break
    message = str(root).lower()
    if isinstance(root, PermissionError) or "permission denied" in message:
        cause = "no permission to read/write the database path."
        step = "check folder permissions and run tz-player again."
    elif "readonly" in message:
        cause = "the database path is read-only."
        step = "move the data directory to a writable location or fix file attributes."
    elif "unable to open database file" in message:
        cause = "the database path is missing or not writable."
        step = "verify the parent directory exists and is writable."
    elif "locked" in message:
        cause = "the database is locked by another process."
        step = "close other tz-player instances and retry."
    elif "malformed" in message or "corrupt" in message:
        cause = "the database file appears corrupt."
        step = "back up then remove the DB file so tz-player can recreate it."
    else:
        cause = "database initialization failed."
        step = "review the log details, then verify DB file access and integrity."
    return (
        "Failed to initialize playlist database.\n"
        f"Likely cause: {cause}\n"
        f"Next step: {step}\n"
        f"DB path: {db_file}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
