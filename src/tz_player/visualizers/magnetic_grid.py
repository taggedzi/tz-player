"""Magnetic-grid distortion visualizer driven by bass/mid/high motion fields."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .base import VisualizerContext, VisualizerFrameInput

_SGR_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


@dataclass
class MagneticGridVisualizer:
    """Render a pulsing grid warped by audio bands and beat events."""

    plugin_id: str = "viz.particle.magnetic_grid"
    display_name: str = "Magnetic Grid Distortion"
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
        field_rows = max(1, height - 2)

        bass, mids, highs = _band_triplet(frame.spectrum_bands)
        beat_onset = bool(frame.beat_is_onset)
        beat_pulse = 1.0 if not beat_onset else 1.8

        cx = (width - 1) / 2.0
        cy = (field_rows - 1) / 2.0
        grid_step_x = max(3, width // 12)
        grid_step_y = max(2, field_rows // 8)

        canvas = [[" " for _ in range(width)] for _ in range(field_rows)]

        for y in range(field_rows):
            for x in range(width):
                if (x % grid_step_x != 0) and (y % grid_step_y != 0):
                    continue
                dx = x - cx
                dy = y - cy
                radius = math.sqrt((dx * dx) + (dy * dy)) + 1.0
                angle = math.atan2(dy, dx)

                vertical_bend = math.sin((frame.frame_index * 0.16) + (x * 0.08)) * (
                    bass * 2.3
                )
                horizontal_wave = math.cos((frame.frame_index * 0.12) + (y * 0.18)) * (
                    mids * 2.0
                )
                jitter = math.sin(
                    (frame.frame_index * 0.40) + (x * 0.23) + (y * 0.17)
                ) * (highs * 1.4)
                pulse = (
                    math.sin((radius * 0.22) - (frame.frame_index * 0.45))
                    * bass
                    * beat_pulse
                )

                nx = int(
                    round(x + horizontal_wave + (math.cos(angle) * pulse) + jitter)
                )
                ny = int(
                    round(y + vertical_bend + (math.sin(angle) * pulse * 0.56) + jitter)
                )
                if 0 <= nx < width and 0 <= ny < field_rows:
                    canvas[ny][nx] = _grid_glyph(
                        x=x, y=y, grid_step_x=grid_step_x, grid_step_y=grid_step_y
                    )

        core_x = int(round(cx))
        core_y = int(round(cy))
        if 0 <= core_x < width and 0 <= core_y < field_rows:
            canvas[core_y][core_x] = "@" if beat_onset else "◉"

        lines = [
            "MAGNETIC GRID DISTORTION",
            _status_line(beat_onset=beat_onset, bass=bass, mids=mids, highs=highs),
        ]
        lines.extend(
            _render_rows(canvas, ansi_enabled=self._ansi_enabled, beat_onset=beat_onset)
        )
        return _fit_lines(lines, width, height)


def _band_triplet(bands: bytes | None) -> tuple[float, float, float]:
    if not bands:
        return (0.0, 0.0, 0.0)
    size = len(bands)
    third = max(1, size // 3)
    bass = bands[:third]
    mids = bands[third : third * 2] or bass
    highs = bands[third * 2 :] or mids
    bass_v = sum(bass) / (len(bass) * 255.0)
    mid_v = sum(mids) / (len(mids) * 255.0)
    high_v = sum(highs) / (len(highs) * 255.0)
    return (bass_v, mid_v, high_v)


def _grid_glyph(*, x: int, y: int, grid_step_x: int, grid_step_y: int) -> str:
    vertical = x % grid_step_x == 0
    horizontal = y % grid_step_y == 0
    if vertical and horizontal:
        return "┼"
    if vertical:
        return "│"
    return "─"


def _status_line(*, beat_onset: bool, bass: float, mids: float, highs: float) -> str:
    mode = "GRID PULSE" if beat_onset else "GRID FLOW"
    return (
        f"{mode} | "
        f"BASS {int(round(bass * 100)):3d}% | "
        f"MID {int(round(mids * 100)):3d}% | "
        f"HIGH {int(round(highs * 100)):3d}%"
    )


def _render_rows(
    canvas: list[list[str]], *, ansi_enabled: bool, beat_onset: bool
) -> list[str]:
    if not ansi_enabled:
        return ["".join(row) for row in canvas]
    return [
        "".join(_colorize(cell, beat_onset=beat_onset) for cell in row)
        for row in canvas
    ]


def _colorize(cell: str, *, beat_onset: bool) -> str:
    if cell == " ":
        return cell
    if cell in {"─", "│"}:
        return f"\x1b[38;2;112;188;255m{cell}\x1b[0m"
    if cell == "┼":
        return f"\x1b[38;2;150;228;255m{cell}\x1b[0m"
    if cell == "@":
        return f"\x1b[38;2;255;230;140m{cell}\x1b[0m"
    if beat_onset:
        return f"\x1b[38;2;255;128;128m{cell}\x1b[0m"
    return f"\x1b[38;2;220;232;255m{cell}\x1b[0m"


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
