"""Gravity-well particle visualizer driven by FFT, RMS, and beat events."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from hashlib import sha256

from .base import VisualizerContext, VisualizerFrameInput

_SGR_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


@dataclass
class GravityWellVisualizer:
    """Render an audio-reactive singularity with orbiting particles and beat bursts."""

    plugin_id: str = "viz.particle.gravity_well"
    display_name: str = "Gravity Well Reactor"
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
        seed = _stable_seed(frame.track_path or frame.title or "gravity-well")

        center_x = (width - 1) / 2.0
        center_y = (field_rows - 1) / 2.0
        max_radius = max(1.0, min(width, field_rows * 2) / 2.0)
        base_particles = _particle_count(width, field_rows, rms)
        gravity_strength = 0.35 + (bass * 0.95)

        canvas = [[" " for _ in range(width)] for _ in range(field_rows)]

        for idx in range(base_particles):
            orbit = 0.18 + (((idx * 23) % 97) / 100.0)
            angle = math.radians(
                (
                    (seed % 360)
                    + (idx * 137.5)
                    + (frame.frame_index * (0.7 + (orbit * 1.2)))
                )
                % 360.0
            )

            distance_phase = (frame.frame_index * 0.12 * orbit) + (idx * 0.19)
            collapse = max(0.12, 1.0 - (gravity_strength * 0.55))
            radius = ((math.sin(distance_phase) + 1.0) * 0.5) * max_radius * collapse
            if beat_onset:
                radius = min(max_radius, radius + (max_radius * (0.28 + (bass * 0.20))))

            px = int(round(center_x + (math.cos(angle) * radius)))
            py = int(round(center_y + (math.sin(angle) * radius * 0.56)))
            if 0 <= px < width and 0 <= py < field_rows:
                canvas[py][px] = _particle_glyph(idx, highs, beat_onset)

        if beat_onset:
            _draw_ring(canvas, center_x, center_y, max_radius * (0.44 + (bass * 0.22)))

        core_x = int(round(center_x))
        core_y = int(round(center_y))
        if 0 <= core_x < width and 0 <= core_y < field_rows:
            canvas[core_y][core_x] = "@" if beat_onset else "◉"

        lines = [
            "GRAVITY WELL REACTOR",
            _status_line(frame, rms=rms, bass=bass, highs=highs),
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
    start = max(0, int(len(bands) * 0.72))
    tail = bands[start:] or bands
    return sum(tail) / (len(tail) * 255.0)


def _stable_seed(value: str) -> int:
    digest = sha256(value.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _particle_count(width: int, rows: int, rms: float) -> int:
    area = max(1, width * rows)
    budget = max(40, min(220, area // 4))
    return max(20, min(220, int(round(budget * (0.25 + (rms * 0.75))))))


def _particle_glyph(index: int, highs: float, beat_onset: bool) -> str:
    glyphs = ".:*+xX"
    if highs >= 0.60:
        glyphs = ".:*+xX#"
    if beat_onset:
        glyphs = "·:*+xX#"
    return glyphs[index % len(glyphs)]


def _draw_ring(
    canvas: list[list[str]], center_x: float, center_y: float, radius: float
) -> None:
    if radius <= 0:
        return
    rows = len(canvas)
    cols = len(canvas[0]) if rows else 0
    samples = max(32, int(radius * 10))
    for idx in range(samples):
        angle = (2.0 * math.pi * idx) / samples
        px = int(round(center_x + (math.cos(angle) * radius)))
        py = int(round(center_y + (math.sin(angle) * radius * 0.56)))
        if 0 <= px < cols and 0 <= py < rows and canvas[py][px] == " ":
            canvas[py][px] = "o"


def _status_line(
    frame: VisualizerFrameInput, *, rms: float, bass: float, highs: float
) -> str:
    beat = "BURST" if frame.beat_is_onset else "COLLAPSE"
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
    if cell in {".", "·", ":"}:
        return f"\x1b[38;2;64;216;255m{cell}\x1b[0m"
    if cell in {"*", "+", "x"}:
        return f"\x1b[38;2;255;188;66m{cell}\x1b[0m"
    if cell in {"X", "#", "o"}:
        return f"\x1b[38;2;255;92;92m{cell}\x1b[0m"
    if beat_onset:
        return f"\x1b[38;2;255;248;140m{cell}\x1b[0m"
    return f"\x1b[38;2;210;230;255m{cell}\x1b[0m"


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
