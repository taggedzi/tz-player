"""Tests for GUI argparse configuration."""

from __future__ import annotations

from tz_player.gui import build_parser
from tz_player.version import PROJECT_URL, __version__


def test_gui_parser_accepts_backend() -> None:
    parser = build_parser()
    args = parser.parse_args(["--backend", "vlc"])
    assert args.backend == "vlc"


def test_gui_parser_defaults_backend_to_vlc() -> None:
    parser = build_parser()
    args = parser.parse_args([])
    assert args.backend == "vlc"


def test_gui_parser_accepts_visualizer_fps() -> None:
    parser = build_parser()
    args = parser.parse_args(["--visualizer-fps", "12"])
    assert args.visualizer_fps == 12


def test_gui_parser_accepts_visualizer_responsiveness_profile() -> None:
    parser = build_parser()
    args = parser.parse_args(["--visualizer-responsiveness", "safe"])
    assert args.visualizer_responsiveness == "safe"


def test_gui_parser_accepts_repeatable_visualizer_plugin_paths() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "--visualizer-plugin-path",
            "plugins.one",
            "--visualizer-plugin-path",
            "plugins.two",
        ]
    )
    assert args.visualizer_plugin_paths == ["plugins.one", "plugins.two"]


def test_gui_parser_accepts_visualizer_plugin_security_mode() -> None:
    parser = build_parser()
    args = parser.parse_args(["--visualizer-plugin-security", "warn"])
    assert args.visualizer_plugin_security == "warn"


def test_gui_parser_accepts_visualizer_plugin_runtime_mode() -> None:
    parser = build_parser()
    args = parser.parse_args(["--visualizer-plugin-runtime", "isolated"])
    assert args.visualizer_plugin_runtime == "isolated"


def test_gui_parser_defaults_visualizer_plugin_paths_to_none() -> None:
    parser = build_parser()
    args = parser.parse_args([])
    assert args.visualizer_plugin_paths is None


def test_gui_help_includes_project_metadata() -> None:
    parser = build_parser()
    help_text = parser.format_help()
    assert f"Project URL: {PROJECT_URL}" in help_text
    assert "Platform: " in help_text
    assert f"Version: {__version__}" in help_text
