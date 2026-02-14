"""Tests for GUI argparse configuration."""

from __future__ import annotations

from tz_player.gui import build_parser


def test_gui_parser_accepts_backend() -> None:
    parser = build_parser()
    args = parser.parse_args(["--backend", "vlc"])
    assert args.backend == "vlc"


def test_gui_parser_accepts_visualizer_fps() -> None:
    parser = build_parser()
    args = parser.parse_args(["--visualizer-fps", "12"])
    assert args.visualizer_fps == 12


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
