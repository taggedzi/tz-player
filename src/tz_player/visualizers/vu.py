"""Audio-reactive VU meter visualizer."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .base import VisualizerContext, VisualizerFrameInput

_SGR_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


@dataclass
class VuReactiveVisualizer:
    plugin_id: str = "vu.reactive"
    display_name: str = "VU Meter (Reactive)"
    _ansi_enabled: bool = True
    _left_smooth: float = 0.0
    _right_smooth: float = 0.0
    _norm_peak: float = 0.35
    _history: list[float] = field(default_factory=list)

    def on_activate(self, context: VisualizerContext) -> None:
        self._ansi_enabled = context.ansi_enabled
        self._left_smooth = 0.0
        self._right_smooth = 0.0
        self._norm_peak = 0.35
        self._history.clear()

    def on_deactivate(self) -> None:
        return None

    def render(self, frame: VisualizerFrameInput) -> str:
        width = max(1, frame.width)
        height = max(1, frame.height)

        live_levels = _extract_live_levels(frame)
        if live_levels is not None:
            left_target, right_target = live_levels
            source = _source_token(frame.level_source)
        else:
            left_target, right_target = _fallback_levels(frame)
            source = "SIM-R"

        left_target, right_target = self._normalize_levels(left_target, right_target)

        self._left_smooth = _smooth(self._left_smooth, left_target)
        self._right_smooth = _smooth(self._right_smooth, right_target)
        mono = (self._left_smooth + self._right_smooth) / 2.0
        self._history.append(mono)
        max_history = max(10, width - 18)
        if len(self._history) > max_history:
            self._history = self._history[-max_history:]

        meter_width = max(8, min(width - 12, 48))
        lines = [
            f"VU REACTIVE [{source}]",
            _source_line(source),
            _meter_line("L", self._left_smooth, meter_width, self._ansi_enabled),
            _meter_line("R", self._right_smooth, meter_width, self._ansi_enabled),
            _meter_line("M", mono, meter_width, self._ansi_enabled),
            _status_line(frame),
        ]
        lines.extend(_history_block(self._history, width, self._ansi_enabled, rows=4))
        return _fit_lines(lines, width, height)

    def _normalize_levels(self, left: float, right: float) -> tuple[float, float]:
        left = _clamp(left)
        right = _clamp(right)
        peak_in = max(left, right)
        decay = 0.97
        self._norm_peak = max(peak_in, self._norm_peak * decay, 0.12)
        gain = 1.0 / self._norm_peak
        return (_boost_level(left, gain), _boost_level(right, gain))


def _extract_live_levels(frame: VisualizerFrameInput) -> tuple[float, float] | None:
    if frame.level_left is None or frame.level_right is None:
        return None
    if not math.isfinite(frame.level_left) or not math.isfinite(frame.level_right):
        return None
    return (_clamp(frame.level_left), _clamp(frame.level_right))


def _fallback_levels(frame: VisualizerFrameInput) -> tuple[float, float]:
    if frame.status not in {"playing", "paused"}:
        return (0.0, 0.0)
    if frame.status == "paused":
        return (0.0, 0.0)
    if frame.volume <= 0:
        return (0.0, 0.0)
    # Pseudo-reactive fallback for backends without level sampling (e.g. VLC).
    t = (frame.position_s * max(frame.speed, 0.1)) + (frame.frame_index / 14.0)
    left = 0.10 + 0.70 * (0.30 + 0.70 * (0.5 + 0.5 * math.sin((t * 5.4) + 0.3)))
    right = 0.10 + 0.70 * (0.30 + 0.70 * (0.5 + 0.5 * math.sin((t * 6.1) + 1.2)))
    return (_clamp(left), _clamp(right))


def _smooth(current: float, target: float) -> float:
    alpha = 0.45 if target > current else 0.22
    return _clamp(current + ((target - current) * alpha))


def _boost_level(value: float, gain: float) -> float:
    noise_floor = 0.01
    raw = max(0.0, value - noise_floor)
    boosted = _clamp(raw * gain * 1.15)
    if boosted <= 0.0:
        return 0.0
    # Slight curve to make low-but-real signal levels more visible.
    return _clamp(boosted**0.82)


def _meter_line(label: str, value: float, width: int, ansi_enabled: bool) -> str:
    fill = int(round(_clamp(value) * width))
    empty = max(0, width - fill)
    bar = _color_meter(fill, empty, width, ansi_enabled)
    pct = int(round(_clamp(value) * 100))
    return f"{label} [{bar}] {pct:3d}%"


def _color_meter(fill: int, empty: int, width: int, ansi_enabled: bool) -> str:
    if not ansi_enabled:
        return ("#" * fill) + ("-" * empty)
    green_end = int(width * 0.7)
    yellow_end = int(width * 0.9)
    parts: list[str] = []
    for idx in range(fill):
        if idx < green_end:
            parts.append("\x1b[38;2;53;230;138m#\x1b[0m")
        elif idx < yellow_end:
            parts.append("\x1b[38;2;242;201;76m#\x1b[0m")
        else:
            parts.append("\x1b[38;2;255;90;54m#\x1b[0m")
    if empty > 0:
        parts.append("-" * empty)
    return "".join(parts)


def _status_line(frame: VisualizerFrameInput) -> str:
    if (
        frame.duration_s is not None
        and math.isfinite(frame.duration_s)
        and frame.duration_s > 0
        and math.isfinite(frame.position_s)
    ):
        pct = min(max(frame.position_s / frame.duration_s, 0.0), 1.0)
    else:
        pct = 0.0
    return (
        f"STATE {frame.status.upper()} | "
        f"TIME {_fmt_clock(frame.position_s)}/{_fmt_clock(frame.duration_s)} | "
        f"{int(round(pct * 100)):3d}%"
    )


def _source_line(source: str) -> str:
    if source == "LIVE":
        return "SRC LIVE LEVELS"
    if source == "ENVELOPE":
        return "SRC ENVELOPE CACHE"
    return "SRC SIMULATED FALLBACK"


def _source_token(level_source: str | None) -> str:
    if level_source == "live":
        return "LIVE"
    if level_source == "envelope":
        return "ENVELOPE"
    return "SIM-R"


def _history_block(
    history: list[float], width: int, ansi_enabled: bool, *, rows: int = 4
) -> list[str]:
    rows = max(1, rows)
    span = max(8, min(width - 3, 64))
    recent = history[-span:] if history else []
    levels = [min(1.0, _clamp(level) ** 0.65) for level in recent]
    lines: list[str] = []
    for row_idx in range(rows):
        threshold = (rows - row_idx) / rows
        row_chars: list[str] = []
        for level in levels:
            if level >= threshold:
                if ansi_enabled:
                    row_chars.append(_level_glyph(level))
                else:
                    row_chars.append("█")
            else:
                row_chars.append("·")
        body = "".join(row_chars).rjust(span, "·")
        prefix = "H " if row_idx == 0 else "  "
        lines.append(f"{prefix}{body}")
    return lines


def _level_glyph(level: float) -> str:
    if level < 0.7:
        return "\x1b[38;2;53;230;138m█\x1b[0m"
    if level < 0.9:
        return "\x1b[38;2;242;201;76m█\x1b[0m"
    return "\x1b[38;2;255;90;54m█\x1b[0m"


def _fit_lines(lines: list[str], width: int, height: int) -> str:
    clipped = [_pad_line(line, width) for line in lines[:height]]
    while len(clipped) < height:
        clipped.append(" " * width)
    return "\n".join(clipped)


def _fmt_clock(value: float | None) -> str:
    if value is None or not math.isfinite(value) or value < 0:
        return "--:--"
    total = int(value)
    mins, secs = divmod(total, 60)
    return f"{mins:02d}:{secs:02d}"


def _clamp(value: float) -> float:
    normalized = float(value)
    if not math.isfinite(normalized):
        return 0.0
    return max(0.0, min(1.0, normalized))


def _pad_line(text: str, width: int) -> str:
    visible = len(_strip_sgr(text))
    if visible > width:
        return _truncate_ansi(text, width)
    if visible < width:
        return text + (" " * (width - visible))
    return text


def _truncate_ansi(text: str, width: int) -> str:
    parts = _SGR_PATTERN.split(text)
    codes = _SGR_PATTERN.findall(text)
    out: list[str] = []
    remaining = width
    for idx, chunk in enumerate(parts):
        if remaining <= 0:
            break
        if chunk:
            take = min(len(chunk), remaining)
            out.append(chunk[:take])
            remaining -= take
        if idx < len(codes):
            out.append(codes[idx])
    return "".join(out)


def _strip_sgr(text: str) -> str:
    return _SGR_PATTERN.sub("", text)
