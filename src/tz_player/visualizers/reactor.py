"""Particle reactor visualizer driven by beat, level, and FFT aggregates."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from hashlib import sha256

from .base import VisualizerContext, VisualizerFrameInput

_SGR_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


@dataclass
class ParticleReactorVisualizer:
    """Render a deterministic radial particle field with beat bursts."""

    plugin_id: str = "viz.reactor.particles"
    display_name: str = "Particle Reactor"
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

        mono = _mono_level(frame)
        bass = _bass_energy(frame.spectrum_bands)
        high = _high_energy(frame.spectrum_bands)
        beat_onset = bool(frame.beat_is_onset)
        seed = _stable_seed(frame.track_path or frame.title or "reactor")
        count = _particle_count(width, field_rows, mono, bass)

        canvas = [[" " for _ in range(width)] for _ in range(field_rows)]
        cx = (width - 1) / 2.0
        cy = (field_rows - 1) / 2.0
        max_radius = max(1.0, min(width, field_rows * 2) / 2.0)
        pulse_scale = 1.8 if beat_onset else 1.0
        angular_speed = 0.8 + (bass * 2.5)

        for idx in range(count):
            angle = math.radians(
                ((seed % 360) + (idx * 137.5) + (frame.frame_index * angular_speed))
                % 360.0
            )
            speed = 0.45 + (((idx * 17) % 101) / 100.0) * (1.0 + bass)
            radius = (
                ((frame.frame_index * speed * 0.22) + ((idx % 11) * 0.31)) % max_radius
            ) * pulse_scale
            radius = min(max_radius, radius)
            px = int(round(cx + (math.cos(angle) * radius)))
            py = int(round(cy + (math.sin(angle) * radius * 0.55)))
            if 0 <= px < width and 0 <= py < field_rows:
                glyph = _particle_glyph(idx, high, beat_onset)
                canvas[py][px] = glyph

        core = "@" if beat_onset else "O"
        core_x = int(round(cx))
        core_y = int(round(cy))
        if 0 <= core_x < width and 0 <= core_y < field_rows:
            canvas[core_y][core_x] = core

        lines = [
            "PARTICLE REACTOR",
            _status_line(frame, mono=mono, bass=bass, high=high),
        ]
        lines.extend(
            _render_field_rows(
                canvas, ansi_enabled=self._ansi_enabled, beat_onset=beat_onset
            )
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
    start = max(0, int(len(bands) * 0.75))
    chunk = bands[start:] or bands
    return sum(chunk) / (len(chunk) * 255.0)


def _stable_seed(value: str) -> int:
    digest = sha256(value.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _particle_count(width: int, rows: int, mono: float, bass: float) -> int:
    area = max(1, width * rows)
    budget = max(20, min(320, area // 3))
    intensity = 0.20 + (mono * 0.55) + (bass * 0.25)
    count = int(round(budget * intensity))
    return max(8, min(320, count))


def _particle_glyph(idx: int, high: float, beat_onset: bool) -> str:
    glyphs = ".:*+o"
    if high >= 0.65:
        glyphs = ".:*+o#"
    if beat_onset:
        glyphs = ".*+o#@"
    return glyphs[idx % len(glyphs)]


def _status_line(
    frame: VisualizerFrameInput, *, mono: float, bass: float, high: float
) -> str:
    beat = "ONSET" if frame.beat_is_onset else "IDLE"
    return (
        f"BEAT {beat} | "
        f"RMS {int(round(mono * 100)):3d}% | "
        f"BASS {int(round(bass * 100)):3d}% | "
        f"HIGH {int(round(high * 100)):3d}%"
    )


def _render_field_rows(
    canvas: list[list[str]], *, ansi_enabled: bool, beat_onset: bool
) -> list[str]:
    if not ansi_enabled:
        return ["".join(row) for row in canvas]
    return [
        "".join(_colorize(glyph, beat_onset=beat_onset) for glyph in row)
        for row in canvas
    ]


def _colorize(glyph: str, *, beat_onset: bool) -> str:
    if glyph == " ":
        return glyph
    if glyph in {".", ":"}:
        return f"\x1b[38;2;53;230;138m{glyph}\x1b[0m"
    if glyph in {"*", "+", "o"}:
        return f"\x1b[38;2;242;201;76m{glyph}\x1b[0m"
    if beat_onset and glyph in {"@", "#"}:
        return f"\x1b[38;2;255;90;54m{glyph}\x1b[0m"
    return f"\x1b[38;2;160;220;255m{glyph}\x1b[0m"


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
