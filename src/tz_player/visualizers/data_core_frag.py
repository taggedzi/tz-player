"""Data-core fragmentation visualizer with center-out shard bursts."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from hashlib import sha256

from .base import VisualizerContext, VisualizerFrameInput

_SGR_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


@dataclass
class DataCoreFragVisualizer:
    """Render a central core that emits reactive shard/particle fragments."""

    plugin_id: str = "viz.particle.data_core_frag"
    display_name: str = "Data Core Fragmentation"
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
        seed = _stable_seed(frame.track_path or frame.title or "data-core-frag")

        cx = (width - 1) / 2.0
        cy = (field_rows - 1) / 2.0
        max_radius = max(3.0, min(width, field_rows * 2) * 0.52)

        shard_count = 20 + int(round((bass * 55) + (mids * 35)))
        micro_count = 10 + int(round(highs * 90))
        if beat_onset:
            shard_count += 26
            micro_count += 24
        shard_count = max(18, min(220, shard_count))
        micro_count = max(8, min(180, micro_count))

        canvas = [[" " for _ in range(width)] for _ in range(field_rows)]

        for idx in range(shard_count):
            angle = math.radians(
                (
                    (seed % 360)
                    + (idx * (360.0 / max(1, shard_count)))
                    + (frame.frame_index * (0.9 + (mids * 1.1)))
                )
                % 360.0
            )
            speed = 0.28 + ((idx * 17) % 23) / 25.0
            radius = (
                (frame.frame_index * speed * (0.55 + (bass * 0.55))) + (idx * 0.18)
            ) % max_radius
            if beat_onset:
                radius = min(max_radius, radius + (max_radius * 0.22))

            x = int(round(cx + (math.cos(angle) * radius)))
            y = int(round(cy + (math.sin(angle) * radius * 0.56)))
            if 0 <= x < width and 0 <= y < field_rows:
                canvas[y][x] = _shard_glyph(highs=highs, beat_onset=beat_onset, idx=idx)

        for idx in range(micro_count):
            angle = math.radians(
                ((seed % 360) + (idx * 23) + (frame.frame_index * 2.4)) % 360.0
            )
            radius = (
                (frame.frame_index * 0.55 + idx * 0.11) * (0.55 + highs * 0.8)
            ) % max_radius
            x = int(round(cx + (math.cos(angle) * radius)))
            y = int(round(cy + (math.sin(angle) * radius * 0.56)))
            if 0 <= x < width and 0 <= y < field_rows and canvas[y][x] == " ":
                canvas[y][x] = "." if idx % 2 == 0 else "·"

        core_x = int(round(cx))
        core_y = int(round(cy))
        if 0 <= core_x < width and 0 <= core_y < field_rows:
            canvas[core_y][core_x] = "@"

        lines = [
            "DATA CORE FRAGMENTATION",
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


def _shard_glyph(*, highs: float, beat_onset: bool, idx: int) -> str:
    glyphs: tuple[str, ...]
    if beat_onset:
        glyphs = ("#", "X", "x", "+", "*")
    elif highs > 0.55:
        glyphs = ("X", "x", "+", "*")
    else:
        glyphs = ("x", "+", "*")
    return glyphs[idx % len(glyphs)]


def _status_line(*, beat_onset: bool, bass: float, mids: float, highs: float) -> str:
    mode = "FRACTURE" if beat_onset else "DRIFT"
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
        return f"\x1b[38;2;96;188;255m{cell}\x1b[0m"
    if cell in {"*", "+", "x"}:
        return f"\x1b[38;2;166;228;140m{cell}\x1b[0m"
    if cell in {"X", "#"}:
        return f"\x1b[38;2;255;168;86m{cell}\x1b[0m"
    if cell == "@":
        if beat_onset:
            return f"\x1b[38;2;255;236;142m{cell}\x1b[0m"
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
