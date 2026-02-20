"""Spectrogram waterfall visualizer driven by cached FFT bands."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .base import VisualizerContext, VisualizerFrameInput

_SGR_PATTERN = re.compile(r"\x1b\[[0-9;]*m")
_ASCII_RAMP = " .:-=+*#%@"
_UNICODE_RAMP = " ▁▂▃▄▅▆▇█"


@dataclass
class SpectrogramWaterfallVisualizer:
    """Render rolling FFT-band history as a terminal waterfall heatmap."""

    plugin_id: str = "viz.spectrogram.waterfall"
    display_name: str = "Spectrogram Waterfall"
    plugin_api_version: int = 1
    requires_spectrum: bool = True
    _ansi_enabled: bool = True
    _unicode_enabled: bool = True
    _history: list[list[int]] = field(default_factory=list)

    def on_activate(self, context: VisualizerContext) -> None:
        self._ansi_enabled = context.ansi_enabled
        self._unicode_enabled = context.unicode_enabled
        self._history.clear()

    def on_deactivate(self) -> None:
        return None

    def render(self, frame: VisualizerFrameInput) -> str:
        width = max(1, frame.width)
        height = max(1, frame.height)
        grid_height = max(1, height - 2)
        grid_width = max(1, width - 1)
        newest = _collapse_bands(frame.spectrum_bands, grid_width)
        if frame.beat_is_onset:
            newest = [min(255, value + 40) for value in newest]
        self._history.insert(0, newest)
        if len(self._history) > grid_height:
            self._history = self._history[:grid_height]

        lines = [
            "SPECTRO WATERFALL",
            _status_line(frame),
        ]
        for row_idx in range(grid_height):
            row = (
                self._history[row_idx]
                if row_idx < len(self._history)
                else [0] * (grid_width)
            )
            marker = ">" if row_idx == 0 and frame.beat_is_onset else " "
            lines.append(
                marker + _render_row(row, self._ansi_enabled, self._unicode_enabled)
            )
        return _fit_lines(lines, width, height)


def _status_line(frame: VisualizerFrameInput) -> str:
    status = (frame.spectrum_status or "missing").upper()
    source = (frame.spectrum_source or "fallback").upper()
    beat = "ONSET" if frame.beat_is_onset else "IDLE"
    return f"FFT {status} [{source}] BEAT {beat}"


def _collapse_bands(bands: bytes | None, width: int) -> list[int]:
    if not bands:
        return [0] * width
    columns: list[int] = []
    for idx in range(width):
        start = int((idx * len(bands)) / width)
        end = int(((idx + 1) * len(bands)) / width)
        if end <= start:
            end = min(len(bands), start + 1)
        peak = max(bands[start:end]) if start < len(bands) else 0
        columns.append(int(peak))
    return columns


def _render_row(values: list[int], ansi_enabled: bool, unicode_enabled: bool) -> str:
    ramp = _UNICODE_RAMP if unicode_enabled else _ASCII_RAMP
    return "".join(_render_cell(value, ramp, ansi_enabled) for value in values)


def _render_cell(level_u8: int, ramp: str, ansi_enabled: bool) -> str:
    idx = int(round((max(0, min(255, int(level_u8))) / 255.0) * (len(ramp) - 1)))
    glyph = ramp[idx]
    if not ansi_enabled or glyph == " ":
        return glyph
    if level_u8 < 96:
        return f"\x1b[38;2;53;230;138m{glyph}\x1b[0m"
    if level_u8 < 192:
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
