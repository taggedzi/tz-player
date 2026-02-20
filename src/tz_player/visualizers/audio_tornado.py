"""Audio tornado visualizer with spiral rise and beat tightening pulses."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from hashlib import sha256

from .base import VisualizerContext, VisualizerFrameInput

_SGR_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


@dataclass
class AudioTornadoVisualizer:
    """Render a vortex-like particle column driven by FFT and beat energy."""

    plugin_id: str = "viz.particle.audio_tornado"
    display_name: str = "Audio Tornado"
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
        seed = _stable_seed(frame.track_path or frame.title or "audio-tornado")

        cx = (width - 1) / 2.0
        max_radius = max(2.0, width * 0.35)
        density = 24 + int(round((rms * 110) + (highs * 60)))
        turbulence = highs * 1.2
        tighten = 0.68 if beat_onset else 1.0

        canvas = [[" " for _ in range(width)] for _ in range(field_rows)]
        for idx in range(max(18, min(220, density))):
            phase = frame.frame_index * (0.28 + (mids * 0.55)) + (idx * 0.43)
            y_norm = ((idx * 37 + frame.frame_index * 3) % (field_rows * 10)) / (
                field_rows * 10.0
            )
            y = int(round((1.0 - y_norm) * (field_rows - 1)))
            radius = (0.15 + (1.0 - y_norm) * (bass * 0.85 + 0.25)) * max_radius
            radius *= tighten
            angle = phase + (y_norm * 10.0) + ((seed % 360) * 0.01745)
            jitter = math.sin((idx * 0.31) + phase) * turbulence
            x = int(round(cx + (math.cos(angle) * radius) + jitter))
            if 0 <= x < width and 0 <= y < field_rows:
                canvas[y][x] = _tornado_glyph(
                    y_norm=y_norm, highs=highs, beat_onset=beat_onset
                )

        lines = [
            "AUDIO TORNADO",
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


def _tornado_glyph(*, y_norm: float, highs: float, beat_onset: bool) -> str:
    if y_norm < 0.2:
        return "#" if beat_onset else "X"
    if y_norm < 0.45:
        return "x" if highs > 0.55 else "+"
    if y_norm < 0.7:
        return "*"
    return "·" if highs > 0.4 else "."


def _status_line(*, beat_onset: bool, bass: float, mids: float, highs: float) -> str:
    mode = "TIGHTEN" if beat_onset else "SPIRAL"
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
        return f"\x1b[38;2;108;206;255m{cell}\x1b[0m"
    if cell in {"*", "+", "x"}:
        return f"\x1b[38;2;166;238;132m{cell}\x1b[0m"
    if cell in {"X", "#"}:
        return f"\x1b[38;2;255;188;86m{cell}\x1b[0m"
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
