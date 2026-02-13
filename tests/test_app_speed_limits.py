"""Tests for app-level speed bounds."""

from __future__ import annotations

from tz_player.app import _clamp_speed


def test_clamp_speed_bounds() -> None:
    assert _clamp_speed(8.0) == 4.0
    assert _clamp_speed(1.25) == 1.25
    assert _clamp_speed(0.1) == 0.5
