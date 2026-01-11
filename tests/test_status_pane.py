"""Tests for status pane helpers."""

from __future__ import annotations

from tz_player.ui.status_pane import (
    quantize_speed,
    speed_from_fraction,
    time_fraction,
    volume_from_fraction,
)


def test_speed_quantization_and_clamp() -> None:
    assert quantize_speed(0.1) == 0.5
    assert quantize_speed(8.2) == 8.0
    assert quantize_speed(1.13) == 1.25
    assert speed_from_fraction(0.0) == 0.5
    assert speed_from_fraction(1.0) == 8.0


def test_volume_clamp() -> None:
    assert volume_from_fraction(-0.2) == 0
    assert volume_from_fraction(1.2) == 100
    assert volume_from_fraction(0.33) == 33


def test_time_fraction_guard() -> None:
    assert time_fraction(1000, 0) == 0.0
    assert time_fraction(500, 1000) == 0.5
    assert time_fraction(1500, 1000) == 1.0
