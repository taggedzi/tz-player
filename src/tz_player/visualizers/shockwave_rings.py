"""Shockwave-ring visualizer driven by beat events and FFT energy."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .base import VisualizerContext, VisualizerFrameInput

_SGR_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


@dataclass
class ShockwaveRingsVisualizer:
    """Render expanding fragmented rings with beat-driven surges."""

    plugin_id: str = "viz.particle.shockwave_rings"
    display_name: str = "Shockwave Rings"
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

        rms = _mono_level(frame)
        bass = _bass_energy(frame.spectrum_bands)
        highs = _high_energy(frame.spectrum_bands)
        beat_onset = bool(frame.beat_is_onset)
        beat_strength = max(0.0, min(1.0, float(frame.beat_strength or 0.0)))

        center_x = (width - 1) / 2.0
        center_y = (field_rows - 1) / 2.0
        max_radius = max(1.0, min(width, field_rows * 2) / 2.0)
        base_radius = (frame.frame_index * (0.32 + (rms * 0.26))) % max_radius

        canvas = [[" " for _ in range(width)] for _ in range(field_rows)]

        ring_count = 2 + int(round(rms * 2.0))
        ring_gap = max(1.0, max_radius / max(3, ring_count + 1))
        thickness = 1 + int(round(bass * 3.0))
        for ring_idx in range(ring_count):
            radius = (base_radius + (ring_idx * ring_gap)) % max_radius
            _draw_ring(
                canvas,
                center_x,
                center_y,
                radius=radius,
                thickness=thickness,
                fragment=highs,
                phase=frame.frame_index + (ring_idx * 17),
                glyph=_ring_glyph(ring_idx),
            )

        if beat_onset:
            burst_radius = min(
                max_radius, (max_radius * 0.36) + (beat_strength * max_radius * 0.38)
            )
            _draw_ring(
                canvas,
                center_x,
                center_y,
                radius=burst_radius,
                thickness=max(thickness + 1, 2),
                fragment=highs * 0.5,
                phase=frame.frame_index + 999,
                glyph="◉",
            )

        core_x = int(round(center_x))
        core_y = int(round(center_y))
        if 0 <= core_x < width and 0 <= core_y < field_rows:
            canvas[core_y][core_x] = "@" if beat_onset else "•"

        lines = [
            "AUDIO SHOCKWAVE RINGS",
            _status_line(beat_onset=beat_onset, bass=bass, highs=highs, rms=rms),
        ]
        lines.extend(
            _render_rows(canvas, ansi_enabled=self._ansi_enabled, beat_onset=beat_onset)
        )
        return _fit_lines(lines, width, height)


def _mono_level(frame: VisualizerFrameInput) -> float:
    levels = [
        value
        for value in (frame.level_left, frame.level_right)
        if value is not None and value >= 0
    ]
    if levels:
        raw = sum(levels) / len(levels)
    else:
        raw = max(0.0, min(1.0, frame.volume / 100.0))
    return max(0.0, min(1.0, float(raw)))


def _bass_energy(bands: bytes | None) -> float:
    if not bands:
        return 0.0
    size = max(1, len(bands) // 4)
    return sum(bands[:size]) / (size * 255.0)


def _high_energy(bands: bytes | None) -> float:
    if not bands:
        return 0.0
    start = max(0, int(len(bands) * 0.7))
    tail = bands[start:] or bands
    return sum(tail) / (len(tail) * 255.0)


def _ring_glyph(index: int) -> str:
    glyphs = ("·", "o", "x", "X")
    return glyphs[index % len(glyphs)]


def _draw_ring(
    canvas: list[list[str]],
    center_x: float,
    center_y: float,
    *,
    radius: float,
    thickness: int,
    fragment: float,
    phase: int,
    glyph: str,
) -> None:
    if radius <= 0:
        return
    rows = len(canvas)
    cols = len(canvas[0]) if rows else 0
    samples = max(36, int(radius * 12))
    skip_stride = max(3, int(round(10 - (fragment * 7))))
    for sample_idx in range(samples):
        if ((sample_idx + phase) % skip_stride) == 0:
            continue
        angle = (2.0 * math.pi * sample_idx) / samples
        for offset in range(thickness):
            draw_radius = max(0.0, radius - (offset * 0.45))
            px = int(round(center_x + (math.cos(angle) * draw_radius)))
            py = int(round(center_y + (math.sin(angle) * draw_radius * 0.56)))
            if 0 <= px < cols and 0 <= py < rows and canvas[py][px] == " ":
                canvas[py][px] = glyph


def _status_line(*, beat_onset: bool, bass: float, highs: float, rms: float) -> str:
    beat = "RING BURST" if beat_onset else "RING FLOW"
    return (
        f"{beat} | "
        f"RMS {int(round(rms * 100)):3d}% | "
        f"BASS {int(round(bass * 100)):3d}% | "
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
    if cell in {"·", "o"}:
        return f"\x1b[38;2;82;214;255m{cell}\x1b[0m"
    if cell in {"x", "X"}:
        return f"\x1b[38;2;255;116;185m{cell}\x1b[0m"
    if cell == "◉":
        return f"\x1b[38;2;255;202;64m{cell}\x1b[0m"
    if beat_onset:
        return f"\x1b[38;2;255;236;140m{cell}\x1b[0m"
    return f"\x1b[38;2;218;230;255m{cell}\x1b[0m"


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
