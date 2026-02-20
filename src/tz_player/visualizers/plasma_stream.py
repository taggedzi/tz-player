"""Plasma-stream visualizer with audio-driven flow-field inversion on beat."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from hashlib import sha256

from .base import VisualizerContext, VisualizerFrameInput

_SGR_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


@dataclass
class PlasmaStreamVisualizer:
    """Render particles advected by an evolving vector flow field."""

    plugin_id: str = "viz.particle.plasma_stream"
    display_name: str = "Plasma Stream Field"
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
        seed = _stable_seed(frame.track_path or frame.title or "plasma-stream")

        cx = (width - 1) * 0.5
        cy = (field_rows - 1) * 0.5
        count = 36 + int(round((mids * 95) + (highs * 55)))
        count = max(24, min(220, count))
        base_speed = 0.65 + (mids * 1.25)
        radial_gain = 0.5 + (bass * 1.2)
        noise_gain = highs * 1.1
        invert = -1.0 if beat_onset else 1.0

        canvas = [[" " for _ in range(width)] for _ in range(field_rows)]
        for idx in range(count):
            base_angle = (seed % 360) * 0.01745 + (idx * 0.31)
            t = frame.frame_index * 0.14
            radius = ((idx * 19 + frame.frame_index * 3) % max(6, width)) * 0.36
            px = cx + math.cos(base_angle + t) * radius
            py = cy + math.sin(base_angle * 0.9 + t * 1.1) * radius * 0.56

            dx = px - cx
            dy = py - cy
            r = math.sqrt((dx * dx) + (dy * dy)) + 1.0
            angle = math.atan2(dy, dx)

            swirl_x = -math.sin(angle + (t * 0.9))
            swirl_y = math.cos(angle + (t * 0.9)) * 0.56
            radial_x = math.cos(angle) * radial_gain
            radial_y = math.sin(angle) * radial_gain * 0.56
            noise = math.sin((idx * 0.17) + t * 1.7 + r * 0.06) * noise_gain

            flow_x = (swirl_x + radial_x * invert + noise) * base_speed
            flow_y = (swirl_y + radial_y * invert + noise * 0.35) * base_speed
            x = int(round(px + flow_x))
            y = int(round(py + flow_y))
            if 0 <= x < width and 0 <= y < field_rows:
                canvas[y][x] = _plasma_glyph(
                    idx=idx, highs=highs, beat_onset=beat_onset
                )

        core_x = int(round(cx))
        core_y = int(round(cy))
        if 0 <= core_x < width and 0 <= core_y < field_rows:
            canvas[core_y][core_x] = "@" if beat_onset else "◉"

        lines = [
            "PLASMA STREAM FIELD",
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


def _stable_seed(value: str) -> int:
    digest = sha256(value.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _plasma_glyph(*, idx: int, highs: float, beat_onset: bool) -> str:
    glyphs: tuple[str, ...]
    if beat_onset:
        glyphs = ("#", "X", "x", "+", "*", "·")
    elif highs > 0.55:
        glyphs = ("X", "x", "+", "*", "·")
    else:
        glyphs = ("x", "+", "*", ".")
    return glyphs[idx % len(glyphs)]


def _status_line(*, beat_onset: bool, bass: float, mids: float, highs: float) -> str:
    mode = "FIELD INVERT" if beat_onset else "FIELD FLOW"
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
    if cell in {".", "·"}:
        return f"\x1b[38;2;98;198;255m{cell}\x1b[0m"
    if cell in {"*", "+", "x"}:
        return f"\x1b[38;2;146;236;170m{cell}\x1b[0m"
    if cell in {"X", "#"}:
        return f"\x1b[38;2;255;186;92m{cell}\x1b[0m"
    if cell == "@":
        if beat_onset:
            return f"\x1b[38;2;255;238;150m{cell}\x1b[0m"
        return f"\x1b[38;2;210;232;255m{cell}\x1b[0m"
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
