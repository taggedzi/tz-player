"""Textual TUI app for tz-player."""

from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import replace
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Static

from . import __version__
from .logging_utils import setup_logging
from .paths import db_path, log_dir, state_path
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
        ("q", "quit", "Quit"),
    ]

    def __init__(self, *, auto_init: bool = True) -> None:
        super().__init__()
        self.store = PlaylistStore(db_path())
        self.state = AppState()
        self.playlist_id: int | None = None
        self._auto_init = auto_init

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
        yield Static("Status: seek --:-- | vol 100% | speed 1.0x", id="status-pane")
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
            pane = self.query_one(PlaylistPane)
            await pane.configure(self.store, playlist_id, self.state.current_track_id)
            pane.focus()
        except Exception as exc:
            logger.exception("Failed to initialize app: %s", exc)
            await self.push_screen(ErrorModal("Failed to initialize. See log file."))

    def action_dismiss_modal(self) -> None:
        if isinstance(self.screen, ModalScreen):
            self.pop_screen()

    def action_focus_find(self) -> None:
        self.query_one(PlaylistPane).focus_find()

    def action_play_pause(self) -> None:
        logger.info("Play/pause not implemented yet.")

    async def action_quit(self) -> None:
        self.exit()


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
