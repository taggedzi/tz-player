"""GUI entry point for tz-player."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .app import TzPlayerApp
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
        )
        logging.getLogger(__name__).info("Starting tz-player GUI")
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
        logging.getLogger(__name__).exception("Fatal GUI startup error: %s", exc)
        print(
            "GUI startup failed. Verify backend/log configuration and re-run with --verbose.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
