"""Command-line interface for tz-player."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .logging_utils import setup_logging
from .paths import log_dir
from .runtime_config import resolve_log_level


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
    logger = logging.getLogger(__name__)
    try:
        level = resolve_log_level(verbose=args.verbose, quiet=args.quiet)
        setup_logging(
            log_dir=log_dir(),
            level=level,
            log_file=Path(args.log_file) if args.log_file else None,
        )
        logger.info("Starting tz-player CLI")
        print("tz-player CLI is ready.")
        return 0
    except Exception as exc:  # pragma: no cover - top-level safety net
        logger.exception("Unhandled error: %s", exc)
        print("Unexpected error. Re-run with --verbose for details.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
