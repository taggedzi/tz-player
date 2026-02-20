"""Spectral landscape visualizer that renders FFT as layered terrain."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .base import VisualizerContext, VisualizerFrameInput

_SGR_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


@dataclass
class AudioTerrainVisualizer:
    """Render grouped FFT bands as an animated mountain-style landscape."""

    plugin_id: str = "viz.spectrum.terrain"
    display_name: str = "Audio Terrain"
    plugin_api_version: int = 1
    requires_spectrum: bool = True
    _ansi_enabled: bool = True

    def on_activate(self, context: VisualizerContext) -> None:
        self._ansi_enabled = context.ansi_enabled

    def on_deactivate(self) -> None:
        return None

    def render(self, frame: VisualizerFrameInput) -> str:
        width = max(1, frame.width)
        height = max(1, frame.height)
        chart_rows = max(1, height - 2)
        columns = _collapse_bands(frame.spectrum_bands, width)
        peaks = _terrain_heights(columns, chart_rows, frame.beat_is_onset)
        lines = [
            "AUDIO TERRAIN",
            _status_line(frame),
        ]
        lines.extend(_render_terrain(peaks, chart_rows, self._ansi_enabled))
        return _fit_lines(lines, width, height)


def _status_line(frame: VisualizerFrameInput) -> str:
    status = (frame.spectrum_status or "missing").upper()
    source = (frame.spectrum_source or "fallback").upper()
    beat = "ONSET" if frame.beat_is_onset else "IDLE"
    return f"FFT {status} [{source}] BEAT {beat}"


def _collapse_bands(bands: bytes | None, width: int) -> list[int]:
    if not bands:
        return [0] * width
    out: list[int] = []
    for idx in range(width):
        start = int((idx * len(bands)) / width)
        end = int(((idx + 1) * len(bands)) / width)
        if end <= start:
            end = min(len(bands), start + 1)
        chunk = bands[start:end] if start < len(bands) else b""
        if not chunk:
            out.append(0)
            continue
        avg = int(round(sum(chunk) / len(chunk)))
        out.append(avg)
    return out


def _terrain_heights(
    values: list[int], rows: int, beat_onset: bool | None
) -> list[int]:
    if not values:
        return []
    peaks: list[int] = []
    beat_lift = 1 if beat_onset and rows > 1 else 0
    for idx, value in enumerate(values):
        left = values[idx - 1] if idx > 0 else value
        right = values[idx + 1] if idx + 1 < len(values) else value
        smoothed = int(round((left + (value * 2) + right) / 4))
        height = int(round((smoothed / 255.0) * (rows - 1))) + beat_lift
        peaks.append(max(0, min(rows - 1, height)))
    return peaks


def _render_terrain(peaks: list[int], rows: int, ansi_enabled: bool) -> list[str]:
    lines: list[str] = []
    width = len(peaks)
    for row_idx in range(rows):
        threshold = rows - 1 - row_idx
        cells: list[str] = []
        for col_idx in range(width):
            peak = peaks[col_idx]
            if peak < threshold:
                cells.append(" ")
                continue
            if peak == threshold:
                cells.append(_terrain_top(peak, rows, ansi_enabled))
                continue
            cells.append(_terrain_fill(col_idx, peak, rows, ansi_enabled))
        lines.append("".join(cells))
    return lines


def _terrain_top(peak: int, rows: int, ansi_enabled: bool) -> str:
    glyph = "^"
    if not ansi_enabled:
        return glyph
    return f"{_terrain_color(peak, rows)}{glyph}\x1b[0m"


def _terrain_fill(col_idx: int, peak: int, rows: int, ansi_enabled: bool) -> str:
    glyph = "#" if (col_idx % 3 == 0) else ":"
    if not ansi_enabled:
        return glyph
    return f"{_terrain_color(peak, rows)}{glyph}\x1b[0m"


def _terrain_color(level: int, rows: int) -> str:
    if rows <= 1:
        return "\x1b[38;2;53;230;138m"
    ratio = max(0.0, min(1.0, level / (rows - 1)))
    if ratio < 0.4:
        return "\x1b[38;2;53;230;138m"
    if ratio < 0.75:
        return "\x1b[38;2;242;201;76m"
    return "\x1b[38;2;255;90;54m"


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
