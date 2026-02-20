"""Colorful waveform-proxy visualizer with neon ribbon styling."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .base import VisualizerContext, VisualizerFrameInput

_SGR_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


@dataclass
class WaveformNeonVisualizer:
    """Render a colorful proxy-wave ribbon from cached waveform min/max data."""

    plugin_id: str = "viz.waveform.neon"
    display_name: str = "Waveform Neon"
    plugin_api_version: int = 1
    requires_waveform: bool = True
    _ansi_enabled: bool = True

    def on_activate(self, context: VisualizerContext) -> None:
        self._ansi_enabled = context.ansi_enabled

    def on_deactivate(self) -> None:
        return None

    def render(self, frame: VisualizerFrameInput) -> str:
        width = max(24, frame.width)
        height = max(6, frame.height)
        chart_height = max(2, height - 2)
        status = frame.waveform_status or "missing"
        source = frame.waveform_source or "fallback"

        left_min, left_max, right_min, right_max = _resolve_ranges(frame)
        left_center = (left_min + left_max) * 0.5
        right_center = (right_min + right_max) * 0.5
        left_amp = max(0.05, (left_max - left_min) * 0.5)
        right_amp = max(0.05, (right_max - right_min) * 0.5)

        canvas = [[" " for _ in range(width)] for _ in range(chart_height)]
        for x in range(width):
            phase = (frame.frame_index * 0.23) + (x * 0.21)
            left_value = _clamp(left_center + (math.sin(phase) * left_amp))
            right_value = _clamp(
                right_center + (math.cos((phase * 0.92) + 0.7) * right_amp)
            )
            left_y = _to_row(left_value, chart_height)
            right_y = _to_row(right_value, chart_height)
            _set_glow(canvas, x, left_y, primary=True)
            _set_glow(canvas, x, right_y, primary=False)

        lines = [
            f"WaveformNeon [{source}/{status}]",
            _render_status_line(left_amp, right_amp, width),
        ]
        lines.extend(_render_canvas(canvas, ansi_enabled=self._ansi_enabled))
        return _fit_lines(lines, width, height)


def _resolve_ranges(
    frame: VisualizerFrameInput,
) -> tuple[float, float, float, float]:
    if (
        frame.waveform_min_left is not None
        and frame.waveform_max_left is not None
        and frame.waveform_min_right is not None
        and frame.waveform_max_right is not None
    ):
        return (
            _clamp(frame.waveform_min_left),
            _clamp(frame.waveform_max_left),
            _clamp(frame.waveform_min_right),
            _clamp(frame.waveform_max_right),
        )
    left = _clamp(frame.level_left or 0.0)
    right = _clamp(frame.level_right or 0.0)
    return (-left, left, -right, right)


def _set_glow(canvas: list[list[str]], x: int, y: int, *, primary: bool) -> None:
    height = len(canvas)
    if not (0 <= y < height):
        return
    if primary:
        canvas[y][x] = "●"
    elif canvas[y][x] == "●":
        canvas[y][x] = "◆"
    else:
        canvas[y][x] = "■"
    for ny in (y - 1, y + 1):
        if 0 <= ny < height and canvas[ny][x] == " ":
            canvas[ny][x] = "·"


def _render_status_line(left_amp: float, right_amp: float, width: int) -> str:
    text = (
        f"L span {int(round(left_amp * 200)):3d}% "
        f"| R span {int(round(right_amp * 200)):3d}%"
    )
    if len(text) > width:
        return text[:width]
    return text


def _render_canvas(canvas: list[list[str]], *, ansi_enabled: bool) -> list[str]:
    if not ansi_enabled:
        return ["".join(row) for row in canvas]
    return ["".join(_colorize(cell) for cell in row) for row in canvas]


def _colorize(cell: str) -> str:
    if cell == " ":
        return cell
    if cell == "·":
        return f"\x1b[38;2;66;245;224m{cell}\x1b[0m"
    if cell == "●":
        return f"\x1b[38;2;62;132;255m{cell}\x1b[0m"
    if cell == "■":
        return f"\x1b[38;2;255;77;163m{cell}\x1b[0m"
    return f"\x1b[38;2;255;194;62m{cell}\x1b[0m"


def _to_row(value: float, height: int) -> int:
    normalized = (_clamp(value) + 1.0) * 0.5
    return max(0, min(height - 1, int(round((1.0 - normalized) * (height - 1)))))


def _fit_lines(lines: list[str], width: int, height: int) -> str:
    clipped = [_pad_line(line, width) for line in lines[:height]]
    while len(clipped) < height:
        clipped.append(" " * width)
    return "\n".join(clipped)


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


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))
