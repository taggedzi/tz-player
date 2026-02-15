"""Tests for app argparse command handling."""

from __future__ import annotations

from tz_player.app import build_parser


def test_app_parser_defaults_to_run_command() -> None:
    parser = build_parser()
    args = parser.parse_args(["--backend", "vlc"])
    assert args.command == "run"
    assert args.backend == "vlc"


def test_app_parser_accepts_doctor_command() -> None:
    parser = build_parser()
    args = parser.parse_args(["doctor", "--backend", "fake"])
    assert args.command == "doctor"
    assert args.backend == "fake"


def test_app_parser_accepts_visualizer_fps() -> None:
    parser = build_parser()
    args = parser.parse_args(["--visualizer-fps", "24"])
    assert args.visualizer_fps == 24


def test_app_parser_accepts_repeatable_visualizer_plugin_paths() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "--visualizer-plugin-path",
            "plugins.alpha",
            "--visualizer-plugin-path",
            "plugins.beta",
        ]
    )
    assert args.visualizer_plugin_paths == ["plugins.alpha", "plugins.beta"]


def test_app_parser_allows_unclamped_visualizer_fps_for_runtime_clamping() -> None:
    parser = build_parser()
    args = parser.parse_args(["--visualizer-fps", "31"])
    assert args.visualizer_fps == 31
