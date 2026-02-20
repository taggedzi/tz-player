"""Tests for runtime config precedence behavior."""

from __future__ import annotations

from tz_player.app import build_parser as app_build_parser
from tz_player.cli import build_parser as cli_build_parser
from tz_player.gui import build_parser as gui_build_parser
from tz_player.runtime_config import (
    normalize_visualizer_responsiveness_profile,
    profile_default_visualizer_fps,
    resolve_log_level,
)


def test_resolve_log_level_precedence_matrix() -> None:
    assert resolve_log_level(verbose=False, quiet=False) == "INFO"
    assert resolve_log_level(verbose=True, quiet=False) == "DEBUG"
    assert resolve_log_level(verbose=False, quiet=True) == "WARNING"
    assert resolve_log_level(verbose=True, quiet=True) == "WARNING"


def test_backend_parser_and_log_resolution_consistent_across_entrypoints() -> None:
    parsers = [app_build_parser(), gui_build_parser(), cli_build_parser()]
    for parser in parsers:
        args = parser.parse_args(["--backend", "vlc", "--verbose", "--quiet"])
        assert args.backend == "vlc"
        assert resolve_log_level(verbose=args.verbose, quiet=args.quiet) == "WARNING"


def test_visualizer_responsiveness_profile_normalization_and_defaults() -> None:
    assert normalize_visualizer_responsiveness_profile("SAFE") == "safe"
    assert normalize_visualizer_responsiveness_profile("balanced") == "balanced"
    assert normalize_visualizer_responsiveness_profile("bad-value") == "balanced"
    assert profile_default_visualizer_fps("safe") == 10
    assert profile_default_visualizer_fps("balanced") == 16
    assert profile_default_visualizer_fps("aggressive") == 22
