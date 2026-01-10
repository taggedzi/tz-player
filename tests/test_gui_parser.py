"""Tests for GUI argparse configuration."""

from __future__ import annotations

from tz_player.gui import build_parser


def test_gui_parser_accepts_backend() -> None:
    parser = build_parser()
    args = parser.parse_args(["--backend", "vlc"])
    assert args.backend == "vlc"
