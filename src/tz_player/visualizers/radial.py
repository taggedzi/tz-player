"""Radial spectrum visualizer for FFT-driven circular analyzer rendering."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .base import VisualizerContext, VisualizerFrameInput

_SGR_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


@dataclass
class RadialSpectrumVisualizer:
    """Render FFT bands as spokes around a center with beat pulse ring."""

    plugin_id: str = "viz.spectrum.radial"
    display_name: str = "Radial Spectrum"
    plugin_api_version: int = 1
    requires_spectrum: bool = True
    requires_beat: bool = True
    _ansi_enabled: bool = True

    def on_activate(self, context: VisualizerContext) -> None:
        self._ansi_enabled = context.ansi_enabled

    def on_deactivate(self) -> None:
        return None

    def render(self, frame: VisualizerFrameInput) -> str:
        width = max(1, frame.width)
        height = max(1, frame.height)
        chart_rows = max(1, height - 2)
        canvas = [[" " for _ in range(width)] for _ in range(chart_rows)]

        cx = (width - 1) / 2.0
        cy = (chart_rows - 1) / 2.0
        base_radius = max(1.0, min(width, chart_rows * 2) / 6.0)
        max_radius = max(base_radius + 1.0, min(width, chart_rows * 2) / 2.3)
        bands = frame.spectrum_bands or b""
        beat_onset = bool(frame.beat_is_onset)
        spoke_count = max(16, min(64, len(bands) if bands else 32))

        for spoke_idx in range(spoke_count):
            level = _band_level(bands, spoke_idx, spoke_count)
            spoke_len = base_radius + ((max_radius - base_radius) * (level / 255.0))
            angle = (2.0 * math.pi * spoke_idx / spoke_count) + (
                (frame.frame_index % 360) * math.pi / 720.0
            )
            _draw_spoke(canvas, cx, cy, angle, spoke_len, level, self._ansi_enabled)

        _draw_core(canvas, cx, cy, beat_onset, self._ansi_enabled)
        if beat_onset:
            _draw_ring(canvas, cx, cy, base_radius + 1.0, self._ansi_enabled)

        lines = [
            "RADIAL SPECTRUM",
            _status_line(frame),
        ]
        lines.extend("".join(row) for row in canvas)
        return _fit_lines(lines, width, height)


def _band_level(bands: bytes, index: int, count: int) -> int:
    if not bands:
        return 0
    start = int((index * len(bands)) / count)
    end = int(((index + 1) * len(bands)) / count)
    if end <= start:
        end = min(len(bands), start + 1)
    chunk = bands[start:end] if start < len(bands) else b""
    if not chunk:
        return 0
    return int(max(chunk))


def _draw_spoke(
    canvas: list[list[str]],
    cx: float,
    cy: float,
    angle: float,
    spoke_len: float,
    level: int,
    ansi_enabled: bool,
) -> None:
    rows = len(canvas)
    cols = len(canvas[0]) if rows else 0
    if rows == 0 or cols == 0:
        return
    steps = max(1, int(round(spoke_len)))
    for step in range(1, steps + 1):
        x = int(round(cx + math.cos(angle) * step))
        y = int(round(cy + math.sin(angle) * step * 0.5))
        if not (0 <= x < cols and 0 <= y < rows):
            continue
        glyph = "." if step < steps else "*"
        canvas[y][x] = _colorize(glyph, level, ansi_enabled)


def _draw_core(
    canvas: list[list[str]], cx: float, cy: float, beat_onset: bool, ansi_enabled: bool
) -> None:
    rows = len(canvas)
    cols = len(canvas[0]) if rows else 0
    x = int(round(cx))
    y = int(round(cy))
    if not (0 <= x < cols and 0 <= y < rows):
        return
    glyph = "@"
    level = 255 if beat_onset else 160
    canvas[y][x] = _colorize(glyph, level, ansi_enabled)


def _draw_ring(
    canvas: list[list[str]], cx: float, cy: float, radius: float, ansi_enabled: bool
) -> None:
    rows = len(canvas)
    cols = len(canvas[0]) if rows else 0
    for angle_idx in range(0, 360, 15):
        angle = math.radians(angle_idx)
        x = int(round(cx + math.cos(angle) * radius))
        y = int(round(cy + math.sin(angle) * radius * 0.5))
        if 0 <= x < cols and 0 <= y < rows:
            canvas[y][x] = _colorize("o", 230, ansi_enabled)


def _status_line(frame: VisualizerFrameInput) -> str:
    status = (frame.spectrum_status or "missing").upper()
    source = (frame.spectrum_source or "fallback").upper()
    beat = "ONSET" if frame.beat_is_onset else "IDLE"
    return f"FFT {status} [{source}] BEAT {beat}"


def _colorize(glyph: str, level: int, ansi_enabled: bool) -> str:
    if not ansi_enabled:
        return glyph
    if level < 96:
        return f"\x1b[38;2;53;230;138m{glyph}\x1b[0m"
    if level < 192:
        return f"\x1b[38;2;242;201;76m{glyph}\x1b[0m"
    return f"\x1b[38;2;255;90;54m{glyph}\x1b[0m"


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
