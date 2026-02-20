"""GUI process entrypoint for the Textual application.

Responsibilities here are intentionally narrow: parse runtime options, set up
logging, instantiate `TzPlayerApp`, and return an exit-code contract that
distinguishes successful startup from fatal initialization failure.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, cast

from . import __version__
from .app import TzPlayerApp
from .logging_utils import setup_logging
from .paths import log_dir
from .runtime_config import VISUALIZER_RESPONSIVENESS_PROFILES, resolve_log_level
from .version import build_help_epilog


def build_parser() -> argparse.ArgumentParser:
    """Build parser for GUI launch and visualizer runtime overrides."""
    parser = argparse.ArgumentParser(
        prog="tz-player",
        description="TaggedZ's command line music player.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=build_help_epilog(),
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
        default="vlc",
        help="Playback backend to use (fake or vlc).",
    )
    parser.add_argument(
        "--visualizer-fps",
        type=int,
        help="Visualizer render cadence (clamped to 2-30 FPS).",
    )
    parser.add_argument(
        "--visualizer-responsiveness",
        choices=VISUALIZER_RESPONSIVENESS_PROFILES,
        help="Visualizer responsiveness profile (safe|balanced|aggressive).",
    )
    parser.add_argument(
        "--visualizer-plugin-path",
        action="append",
        dest="visualizer_plugin_paths",
        help="Local visualizer module/package path (repeatable).",
    )
    parser.add_argument(
        "--visualizer-plugin-security",
        choices=("off", "warn", "enforce"),
        help="Local plugin security policy mode.",
    )
    parser.add_argument(
        "--visualizer-plugin-runtime",
        choices=("in-process", "isolated"),
        help="Local plugin runtime mode.",
    )
    return parser


def main() -> int:
    """Run GUI entrypoint and translate startup outcome to exit code."""
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
        logging.getLogger(__name__).info("Starting tz-player GUI")
        visualizer_fps = getattr(args, "visualizer_fps", None)
        visualizer_responsiveness = getattr(args, "visualizer_responsiveness", None)
        visualizer_plugin_paths = getattr(args, "visualizer_plugin_paths", None)
        visualizer_plugin_security = getattr(args, "visualizer_plugin_security", None)
        visualizer_plugin_runtime = getattr(args, "visualizer_plugin_runtime", None)
        app_kwargs: dict[str, object] = {"backend_name": args.backend}
        if visualizer_fps is not None:
            app_kwargs["visualizer_fps_override"] = visualizer_fps
        if visualizer_responsiveness is not None:
            app_kwargs["visualizer_responsiveness_profile_override"] = (
                visualizer_responsiveness
            )
        if visualizer_plugin_paths is not None:
            app_kwargs["visualizer_plugin_paths_override"] = visualizer_plugin_paths
        if visualizer_plugin_security is not None:
            app_kwargs["visualizer_plugin_security_mode_override"] = (
                visualizer_plugin_security
            )
        if visualizer_plugin_runtime is not None:
            app_kwargs["visualizer_plugin_runtime_mode_override"] = (
                visualizer_plugin_runtime
            )
        app = TzPlayerApp(**cast(dict[str, Any], app_kwargs))
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
