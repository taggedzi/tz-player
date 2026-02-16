"""Tests for CLI argparse configuration."""

from __future__ import annotations

from tz_player.cli import build_parser
from tz_player.version import PROJECT_URL, __version__


def test_cli_parser_accepts_backend() -> None:
    parser = build_parser()
    args = parser.parse_args(["--backend", "vlc"])
    assert args.backend == "vlc"


def test_cli_parser_defaults_backend_to_vlc() -> None:
    parser = build_parser()
    args = parser.parse_args([])
    assert args.backend == "vlc"


def test_cli_help_includes_project_metadata() -> None:
    parser = build_parser()
    help_text = parser.format_help()
    assert f"Project URL: {PROJECT_URL}" in help_text
    assert "Platform: " in help_text
    assert f"Version: {__version__}" in help_text
