"""Tests for app-level speed bounds."""

from __future__ import annotations

import math

from tz_player.app import _clamp_speed


def test_clamp_speed_bounds() -> None:
    assert _clamp_speed(8.0) == 4.0
    assert _clamp_speed(1.25) == 1.25
    assert _clamp_speed(0.1) == 0.5


def test_clamp_speed_handles_non_finite_values() -> None:
    assert _clamp_speed(float("inf")) == 4.0
    assert _clamp_speed(-float("inf")) == 0.5
    assert _clamp_speed(float("nan")) == 0.5
    assert not math.isnan(_clamp_speed(float("nan")))
