"""Textual TUI app for tz-player."""

from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import replace
from pathlib import Path
from typing import Literal, cast

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Static

from . import __version__
from .events import PlayerStateChanged, TrackChanged
from .logging_utils import setup_logging
from .paths import db_path, log_dir, state_path
from .services.metadata_service import MetadataService
from .services.player_service import PlayerService, PlayerState, TrackInfo
from .services.playlist_store import PlaylistStore
from .state_store import AppState, load_state, save_state
from .ui.modals.error import ErrorModal
from .ui.playlist_pane import PlaylistPane

logger = logging.getLogger(__name__)


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

    #playlist-top, #playlist-bottom {
        height: 3;
        content-align: left middle;
    }

    #playlist-actions {
        width: 20;
        margin-right: 1;
    }

    #reorder-up, #reorder-down {
        margin-right: 1;
    }

    #playlist-find {
        width: 1fr;
    }

    #playlist-table {
        height: 1fr;
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
        height: 3;
        border: solid white;
        content-align: center middle;
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
        ("f", "focus_find", "Find"),
        ("n", "next_track", "Next"),
        ("p", "previous_track", "Previous"),
        ("x", "stop", "Stop"),
        ("left", "seek_back", "Seek -5s"),
        ("right", "seek_forward", "Seek +5s"),
        ("home", "seek_start", "Seek start"),
        ("end", "seek_end", "Seek end"),
        ("-", "volume_down", "Vol -"),
        ("+", "volume_up", "Vol +"),
        ("[", "speed_down", "Speed -"),
        ("]", "speed_up", "Speed +"),
        ("\\", "speed_reset", "Speed reset"),
        ("r", "repeat_mode", "Repeat"),
        ("s", "shuffle", "Shuffle"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, *, auto_init: bool = True) -> None:
        super().__init__()
        self.store = PlaylistStore(db_path())
        self.state = AppState()
        self.playlist_id: int | None = None
        self._auto_init = auto_init
        self.player_service: PlayerService | None = None
        self.player_state = PlayerState()
        self.current_track: TrackInfo | None = None
        self.metadata_service: MetadataService | None = None
        self._state_save_task: asyncio.Task[None] | None = None
        self._last_persisted: (
            tuple[int | None, int | None, int, float, str, bool] | None
        ) = None

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
        yield Static(
            "Status: idle | --:--/--:-- | vol 100 | speed 1.00x",
            id="status-pane",
        )
        yield Footer()

    def on_mount(self) -> None:
        if self._auto_init:
            asyncio.create_task(self._initialize_state())

    async def _initialize_state(self) -> None:
        try:
            self.state = await asyncio.to_thread(load_state, state_path())
            await self.store.initialize()
            playlist_id = await self.store.ensure_playlist("Default")
            if self.state.playlist_id != playlist_id:
                self.state = replace(self.state, playlist_id=playlist_id)
                await asyncio.to_thread(save_state, state_path(), self.state)
            self.playlist_id = playlist_id
            self.player_state = self._player_state_from_appstate(playlist_id)
            self.player_service = PlayerService(
                emit_event=self._handle_player_event,
                track_info_provider=self._track_info_provider,
                next_track_provider=self._next_track_provider,
                prev_track_provider=self._prev_track_provider,
                initial_state=self.player_state,
            )
            self.metadata_service = MetadataService(
                self.store, on_metadata_updated=self._handle_metadata_updated
            )
            await self.player_service.start()
            self._last_persisted = self._state_tuple(self.player_state)
            pane = self.query_one(PlaylistPane)
            await pane.configure(
                self.store,
                playlist_id,
                self.state.current_track_id,
                self.metadata_service,
            )
            pane.focus()
            self._update_status_pane()
            self._update_current_track_pane()
        except Exception as exc:
            logger.exception("Failed to initialize app: %s", exc)
            await self.push_screen(ErrorModal("Failed to initialize. See log file."))

    async def on_unmount(self) -> None:
        if self.player_service is not None:
            await self.player_service.shutdown()

    def action_dismiss_modal(self) -> None:
        if isinstance(self.screen, ModalScreen):
            self.pop_screen()

    def action_focus_find(self) -> None:
        self.query_one(PlaylistPane).focus_find()

    async def action_play_pause(self) -> None:
        if self.player_service is None or self.playlist_id is None:
            return
        if self.player_state.track_id is None:
            cursor_id = self.query_one(PlaylistPane).get_cursor_track_id()
            if cursor_id is None:
                return
            await self.player_service.play_track(self.playlist_id, cursor_id)
            return
        await self.player_service.toggle_pause()

    async def action_play_selected(self) -> None:
        if self.player_service is None or self.playlist_id is None:
            return
        cursor_id = self.query_one(PlaylistPane).get_cursor_track_id()
        if cursor_id is None:
            return
        await self.player_service.play_track(self.playlist_id, cursor_id)

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
        await self.player_service.toggle_shuffle()

    async def _handle_player_event(self, event: object) -> None:
        if isinstance(event, PlayerStateChanged):
            self.player_state = event.state
            playing_id = (
                event.state.track_id
                if event.state.status in {"playing", "paused"}
                else None
            )
            self.query_one(PlaylistPane).set_playing_track_id(playing_id)
            self._update_status_pane()
            if self._state_tuple(self.player_state) != self._last_persisted:
                await self._schedule_state_save()
        elif isinstance(event, TrackChanged):
            self.current_track = event.track_info
            self._update_current_track_pane()
            track_id = self.player_state.track_id
            if (
                track_id is not None
                and self.current_track is not None
                and _track_needs_metadata(self.current_track)
                and self.metadata_service is not None
            ):
                self.run_worker(
                    self.metadata_service.ensure_metadata([track_id]),
                    exclusive=False,
                )

    async def _track_info_provider(
        self, playlist_id: int, track_id: int
    ) -> TrackInfo | None:
        row = await self.store.fetch_track(playlist_id, track_id)
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
        self, playlist_id: int, track_id: int, wrap: bool
    ) -> int | None:
        return await self.store.get_next_track_id(playlist_id, track_id, wrap=wrap)

    async def _prev_track_provider(
        self, playlist_id: int, track_id: int, wrap: bool
    ) -> int | None:
        return await self.store.get_prev_track_id(playlist_id, track_id, wrap=wrap)

    def _update_status_pane(self) -> None:
        status = self.player_state.status
        pos = _format_time(self.player_state.position_ms)
        dur = _format_time(self.player_state.duration_ms)
        volume = self.player_state.volume
        speed = self.player_state.speed
        repeat_mode = self.player_state.repeat_mode
        shuffle = "on" if self.player_state.shuffle else "off"
        text = (
            f"Status: {status} | {pos}/{dur} | vol {volume} | "
            f"speed {speed:.2f}x | repeat {repeat_mode} | shuffle {shuffle}"
        )
        self.query_one("#status-pane", Static).update(text)

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

    async def _handle_metadata_updated(self, track_ids: list[int]) -> None:
        pane = self.query_one(PlaylistPane)
        await pane.refresh_view()
        if self.player_state.track_id in track_ids:
            await self._refresh_current_track_info()

    async def _refresh_current_track_info(self) -> None:
        if self.playlist_id is None or self.player_state.track_id is None:
            return
        self.current_track = await self._track_info_provider(
            self.playlist_id, self.player_state.track_id
        )
        self._update_current_track_pane()

    def _player_state_from_appstate(self, playlist_id: int) -> PlayerState:
        repeat_mode = _repeat_from_state(self.state.repeat_mode)
        volume = self.state.volume
        if volume <= 1.0:
            volume = volume * 100
        return PlayerState(
            playlist_id=playlist_id,
            track_id=self.state.current_track_id,
            volume=int(volume),
            speed=self.state.speed,
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
                current_track_id=self.player_state.track_id,
                volume=float(self.player_state.volume),
                speed=self.player_state.speed,
                repeat_mode=self.player_state.repeat_mode.lower(),
                shuffle=self.player_state.shuffle,
            )
            self._last_persisted = self._state_tuple(self.player_state)
            await asyncio.to_thread(save_state, state_path(), self.state)
        except asyncio.CancelledError:
            return

    def _state_tuple(
        self, state: PlayerState
    ) -> tuple[int | None, int | None, int, float, str, bool]:
        return (
            state.playlist_id,
            state.track_id,
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
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    level = "INFO"
    if args.verbose:
        level = "DEBUG"
    if args.quiet:
        level = "WARNING"

    setup_logging(
        log_dir=log_dir(),
        level=level,
        log_file=Path(args.log_file) if args.log_file else None,
    )
    logging.getLogger(__name__).info("Starting tz-player TUI")
    TzPlayerApp().run()


if __name__ == "__main__":
    main()
