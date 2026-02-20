"""Constellation visualizer with star links pulsing from audio energy."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from hashlib import sha256

from .base import VisualizerContext, VisualizerFrameInput

_SGR_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


@dataclass
class ConstellationVisualizer:
    """Render stars and lightweight links that react to beat and FFT energy."""

    plugin_id: str = "viz.particle.constellation"
    display_name: str = "Constellation Mode"
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
        seed = _stable_seed(frame.track_path or frame.title or "constellation")

        star_count = 18 + int(round((mids * 36) + (highs * 22)))
        if beat_onset:
            star_count += 8
        star_count = max(14, min(90, star_count))

        stars = _stars_for_frame(
            width=width,
            rows=field_rows,
            frame_index=frame.frame_index,
            seed=seed,
            count=star_count,
        )
        max_link_dist = 5 + int(round(bass * 8))
        link_stride = max(2, int(round(7 - (highs * 3))))
        links: list[tuple[int, int, int, int]] = []
        for idx, (x1, y1) in enumerate(stars):
            if idx % link_stride != 0:
                continue
            nearest = _nearest_star(idx, stars, max_dist=max_link_dist)
            if nearest is not None:
                x2, y2 = nearest
                links.append((x1, y1, x2, y2))

        canvas = [[" " for _ in range(width)] for _ in range(field_rows)]
        for x1, y1, x2, y2 in links:
            _draw_line(canvas, x1, y1, x2, y2, glyph=_link_glyph(bass, beat_onset))
        for x, y in stars:
            if 0 <= x < width and 0 <= y < field_rows:
                canvas[y][x] = _star_glyph(highs, beat_onset)

        lines = [
            "CONSTELLATION MODE",
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


def _stars_for_frame(
    *, width: int, rows: int, frame_index: int, seed: int, count: int
) -> list[tuple[int, int]]:
    stars: list[tuple[int, int]] = []
    for idx in range(count):
        angle = (frame_index * 0.09) + (idx * 0.63) + ((seed % 360) * 0.01745)
        radius = 0.22 + ((idx * 37 + seed) % 100) / 140.0
        cx = (width - 1) * 0.5
        cy = (rows - 1) * 0.5
        x = int(round(cx + math.cos(angle) * width * 0.38 * radius))
        y = int(round(cy + math.sin(angle * 1.3) * rows * 0.36 * radius))
        stars.append((max(0, min(width - 1, x)), max(0, min(rows - 1, y))))
    return stars


def _nearest_star(
    index: int, stars: list[tuple[int, int]], *, max_dist: int
) -> tuple[int, int] | None:
    x1, y1 = stars[index]
    best: tuple[int, int] | None = None
    best_d2 = max_dist * max_dist
    for j, (x2, y2) in enumerate(stars):
        if j == index:
            continue
        dx = x2 - x1
        dy = y2 - y1
        d2 = (dx * dx) + (dy * dy)
        if d2 == 0 or d2 > best_d2:
            continue
        best = (x2, y2)
        best_d2 = d2
    return best


def _draw_line(
    canvas: list[list[str]], x1: int, y1: int, x2: int, y2: int, *, glyph: str
) -> None:
    dx = abs(x2 - x1)
    dy = -abs(y2 - y1)
    sx = 1 if x1 < x2 else -1
    sy = 1 if y1 < y2 else -1
    err = dx + dy
    x, y = x1, y1
    rows = len(canvas)
    cols = len(canvas[0]) if rows else 0
    while True:
        if 0 <= x < cols and 0 <= y < rows and canvas[y][x] == " ":
            canvas[y][x] = glyph
        if x == x2 and y == y2:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy


def _star_glyph(highs: float, beat_onset: bool) -> str:
    if beat_onset:
        return "✶"
    if highs > 0.55:
        return "✦"
    return "*"


def _link_glyph(bass: float, beat_onset: bool) -> str:
    if beat_onset:
        return "="
    if bass > 0.45:
        return "-"
    return "."


def _status_line(*, beat_onset: bool, bass: float, mids: float, highs: float) -> str:
    mode = "CLUSTER BURST" if beat_onset else "STAR LINK"
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
    if cell in {".", "-"}:
        return f"\x1b[38;2;110;172;255m{cell}\x1b[0m"
    if cell == "=":
        return f"\x1b[38;2;255;148;148m{cell}\x1b[0m"
    if cell in {"*", "✦"}:
        return f"\x1b[38;2;184;236;255m{cell}\x1b[0m"
    if cell == "✶":
        return f"\x1b[38;2;255;238;152m{cell}\x1b[0m"
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
