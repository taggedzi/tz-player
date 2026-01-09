"""Textual TUI app for tz-player."""

from __future__ import annotations

import argparse
import logging

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Static

from . import __version__
from .logging_utils import setup_logging


class tz-playerApp(App):
    TITLE = "tz-player"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("tz-player TUI is running.")
        yield Footer()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tz-player", description="TaggedZ's command line music player.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("--quiet", action="store_true", help="Only show warnings and errors")
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

    setup_logging(level=level, log_file=args.log_file)
    logging.getLogger(__name__).info("Starting tz-player TUI")
    tz-playerApp().run()


if __name__ == "__main__":
    main()

