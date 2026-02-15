"""Tests for time formatting helpers."""

from __future__ import annotations

from tz_player.utils.time_format import format_time_ms, format_time_pair_ms


def test_format_time_under_hour() -> None:
    assert format_time_ms(0) == "00:00"
    assert format_time_ms(59_000) == "00:59"
    assert format_time_ms(61_000) == "01:01"
    assert format_time_ms(3_599_000) == "59:59"


def test_format_time_at_hour_and_beyond() -> None:
    assert format_time_ms(3_600_000) == "1:00:00"
    assert format_time_ms(36_000_000) == "10:00:00"
    assert format_time_ms(360_000_000) == "100:00:00"


def test_format_time_negative() -> None:
    assert format_time_ms(-5_000) == "00:00"


def test_format_time_pair_hour_mode() -> None:
    pos, dur = format_time_pair_ms(60_000, 3_600_000)
    assert pos == "0:01:00"
    assert dur == "1:00:00"


def test_format_time_pair_under_hour() -> None:
    pos, dur = format_time_pair_ms(60_000, 120_000)
    assert pos == "01:00"
    assert dur == "02:00"


def test_format_time_pair_unknown_duration() -> None:
    pos, dur = format_time_pair_ms(60_000, 0)
    assert pos == "01:00"
    assert dur == "--:--"
    pos, dur = format_time_pair_ms(3_600_000, -1)
    assert pos == "1:00:00"
    assert dur == "--:--:--"


def test_format_time_non_finite_values_fall_back_to_zero() -> None:
    assert format_time_ms(float("nan")) == "00:00"  # type: ignore[arg-type]
    assert format_time_ms(float("inf")) == "00:00"  # type: ignore[arg-type]
