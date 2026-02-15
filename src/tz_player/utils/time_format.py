"""Time formatting helpers for the UI."""

from __future__ import annotations

import math


def format_time_ms(ms: int) -> str:
    """Format milliseconds as MM:SS or H:MM:SS when needed."""
    return _format_time_ms(ms, force_hours=False)


def format_time_pair_ms(position_ms: int, duration_ms: int) -> tuple[str, str]:
    """Format position and duration with consistent width."""
    hours_mode = _needs_hours(position_ms) or _needs_hours(duration_ms)
    position = _format_time_ms(position_ms, force_hours=hours_mode)
    if duration_ms <= 0:
        placeholder = "--:--:--" if hours_mode else "--:--"
        return position, placeholder
    duration = _format_time_ms(duration_ms, force_hours=hours_mode)
    return position, duration


def _needs_hours(ms: int) -> bool:
    return _coerce_ms(ms) >= 3_600_000


def _format_time_ms(ms: int, *, force_hours: bool) -> str:
    total_seconds = _coerce_ms(ms) // 1000
    hours = total_seconds // 3600
    if hours > 0 or force_hours:
        minutes = (total_seconds // 60) % 60
        seconds = total_seconds % 60
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:02d}"


def _coerce_ms(value: int) -> int:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(numeric):
        return 0
    return max(0, int(numeric))
