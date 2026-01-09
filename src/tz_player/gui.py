"""GUI entry point placeholder for tz-player."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from . import __version__
from .logging_utils import setup_logging
from .paths import log_dir


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


def main() -> int:
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
    logging.getLogger(__name__).info("Starting tz-player GUI placeholder")
    print("Add a GUI toolkit (PySide6, Tkinter, etc.) and wire it here.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
