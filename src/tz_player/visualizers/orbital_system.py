"""Orbital-system visualizer with band-split rings and beat velocity pulses."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from hashlib import sha256

from .base import VisualizerContext, VisualizerFrameInput

_SGR_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


@dataclass
class OrbitalSystemVisualizer:
    """Render inner/mid/outer particle orbits mapped to bass/mid/high energy."""

    plugin_id: str = "viz.particle.orbital_system"
    display_name: str = "Orbital Audio System"
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
        bass, mids, highs = _band_triplet(frame.spectrum_bands)
        beat_onset = bool(frame.beat_is_onset)
        seed = _stable_seed(frame.track_path or frame.title or "orbital-system")

        cx = (width - 1) / 2.0
        cy = (field_rows - 1) / 2.0
        max_radius = max(2.0, min(width, field_rows * 2) / 2.0)
        beat_boost = 1.35 if beat_onset else 1.0

        canvas = [[" " for _ in range(width)] for _ in range(field_rows)]
        orbit_specs = (
            ("bass", max(1.8, max_radius * 0.28), bass, "●"),
            ("mid", max(2.2, max_radius * 0.48), mids, "◆"),
            ("high", max(2.6, max_radius * 0.72), highs, "■"),
        )

        for orbit_idx, (_label, base_radius, energy, glyph) in enumerate(orbit_specs):
            radius = min(max_radius, base_radius * (0.88 + (energy * 0.34)))
            count = _orbit_particle_count(radius=radius, energy=energy, rms=rms)
            velocity = (0.45 + (energy * 1.45) + (orbit_idx * 0.18)) * beat_boost
            for particle_idx in range(count):
                angle = math.radians(
                    (
                        (seed % 360)
                        + (particle_idx * (360.0 / max(1, count)))
                        + (frame.frame_index * velocity)
                        + (orbit_idx * 57)
                    )
                    % 360.0
                )
                px = int(round(cx + (math.cos(angle) * radius)))
                py = int(round(cy + (math.sin(angle) * radius * 0.56)))
                if 0 <= px < width and 0 <= py < field_rows:
                    canvas[py][px] = glyph

        core_x = int(round(cx))
        core_y = int(round(cy))
        if 0 <= core_x < width and 0 <= core_y < field_rows:
            canvas[core_y][core_x] = "@" if beat_onset else "◉"

        lines = [
            "ORBITAL AUDIO SYSTEM",
            _status_line(beat_onset=beat_onset, bass=bass, mids=mids, highs=highs),
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


def _orbit_particle_count(*, radius: float, energy: float, rms: float) -> int:
    base = int(round((radius * 3.2) + 8))
    dynamic = int(round((energy * 16) + (rms * 10)))
    return max(10, min(120, base + dynamic))


def _status_line(*, beat_onset: bool, bass: float, mids: float, highs: float) -> str:
    mode = "PULSE" if beat_onset else "STABLE"
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
    if cell == "●":
        return f"\x1b[38;2;255;164;86m{cell}\x1b[0m"
    if cell == "◆":
        return f"\x1b[38;2;90;210;255m{cell}\x1b[0m"
    if cell == "■":
        return f"\x1b[38;2;170;255;132m{cell}\x1b[0m"
    if cell == "@":
        return f"\x1b[38;2;255;238;128m{cell}\x1b[0m"
    if beat_onset:
        return f"\x1b[38;2;255;120;120m{cell}\x1b[0m"
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
