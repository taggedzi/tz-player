"""Reactive particle-rain visualizer with beat acceleration and bass bursts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256

from .base import VisualizerContext, VisualizerFrameInput

_SGR_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


@dataclass
class ReactiveRainVisualizer:
    """Render reverse-matrix style rain that responds to FFT and beat pulses."""

    plugin_id: str = "viz.particle.rain_reactive"
    display_name: str = "Reactive Particle Rain"
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
        seed = _stable_seed(frame.track_path or frame.title or "reactive-rain")

        density = 0.20 + (rms * 0.65)
        speed = 1 + int(round((highs * 2.0) + (1.0 if beat_onset else 0.0)))
        burst_rows = 1 + int(round(bass * 2.0))
        burst_stride = max(5, int(round(16 - (bass * 8.0))))

        canvas = [[" " for _ in range(width)] for _ in range(field_rows)]

        for x in range(width):
            col_seed = seed ^ (x * 1315423911)
            spawn_gate = ((col_seed >> 3) & 1023) / 1023.0
            if spawn_gate > density:
                continue
            trail = 1 + (
                ((col_seed >> 9) + frame.frame_index) % max(2, field_rows // 3)
            )
            head_y = (frame.frame_index * speed + (col_seed % field_rows)) % field_rows
            for offset in range(trail):
                y = head_y - offset
                if y < 0:
                    break
                glyph = _rain_glyph(offset=offset, highs=highs, beat_onset=beat_onset)
                canvas[y][x] = glyph

        base_row = (frame.frame_index * max(1, speed // 2)) % field_rows
        for row_idx in range(burst_rows):
            y = (base_row + row_idx * 2) % field_rows
            for x in range(width):
                if ((x + frame.frame_index + row_idx) % burst_stride) == 0 and canvas[
                    y
                ][x] == " ":
                    canvas[y][x] = "-"

        lines = [
            "REACTIVE PARTICLE RAIN",
            _status_line(beat_onset=beat_onset, rms=rms, bass=bass, highs=highs),
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


def _rain_glyph(*, offset: int, highs: float, beat_onset: bool) -> str:
    if offset == 0:
        return "#" if beat_onset else "X"
    if offset == 1:
        return "x" if highs > 0.5 else "+"
    if offset == 2:
        return "*"
    return "·" if highs > 0.4 else "."


def _status_line(*, beat_onset: bool, rms: float, bass: float, highs: float) -> str:
    mode = "SURGE" if beat_onset else "FLOW"
    return (
        f"{mode} | "
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
    if cell in {".", "·"}:
        return f"\x1b[38;2;92;224;255m{cell}\x1b[0m"
    if cell in {"*", "+", "x"}:
        return f"\x1b[38;2;154;238;110m{cell}\x1b[0m"
    if cell in {"X", "#"}:
        return f"\x1b[38;2;255;196;88m{cell}\x1b[0m"
    if cell == "-":
        if beat_onset:
            return f"\x1b[38;2;255;124;124m{cell}\x1b[0m"
        return f"\x1b[38;2;120;190;255m{cell}\x1b[0m"
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
