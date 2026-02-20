"""Typography-focused visualizer with subtle beat/energy reactive effects."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .base import VisualizerContext, VisualizerFrameInput

_SGR_PATTERN = re.compile(r"\x1b\[[0-9;]*m")
_GLITCH_GLYPHS = "@#$%&*+=?!"


@dataclass
class TypographyGlitchVisualizer:
    """Render centered metadata with restrained glitch and pulse accents."""

    plugin_id: str = "viz.typography.glitch"
    display_name: str = "Typography Glitch"
    plugin_api_version: int = 1
    requires_beat: bool = True
    _ansi_enabled: bool = True

    def on_activate(self, context: VisualizerContext) -> None:
        self._ansi_enabled = context.ansi_enabled

    def on_deactivate(self) -> None:
        return None

    def render(self, frame: VisualizerFrameInput) -> str:
        width = max(1, frame.width)
        height = max(1, frame.height)
        level = _mono_level(frame)
        bass = _bass_energy(frame.spectrum_bands)
        high = _high_energy(frame.spectrum_bands)
        beat_onset = bool(frame.beat_is_onset)

        title = _safe_text(frame.title, fallback=_track_name(frame.track_path))
        subtitle = _safe_text(frame.artist, fallback="Unknown Artist")
        album = _safe_text(frame.album, fallback="Unknown Album")
        detail = f"{subtitle} - {album}"

        wobble = _wobble_offset(level, bass, frame.frame_index)
        breathing = _breathing_pad(level)
        title_text = _glitch_text(title, frame.frame_index, beat_onset)
        detail_text = _glitch_text(detail, frame.frame_index + 11, beat_onset)
        title_line = _centered(title_text, width, wobble=wobble)
        detail_line = _centered(detail_text, width, wobble=-wobble)
        if self._ansi_enabled:
            title_line = _apply_shimmer(title_line, high, beat_onset)

        border_char = "=" if beat_onset else "-"
        top_border = border_char * width
        mid_border = (" " * breathing) + ("·" * max(1, width - (2 * breathing)))
        mid_border = _pad_plain(mid_border[:width], width)
        status = (
            f"{frame.status.upper()} | "
            f"BEAT {'ONSET' if beat_onset else 'IDLE'} | "
            f"RMS {int(round(level * 100)):3d}%"
        )
        info = _pad_plain(status, width)

        lines = [
            top_border,
            info,
            mid_border,
            title_line,
            detail_line,
            mid_border,
            top_border,
        ]
        return _fit_lines(lines, width, height)


def _safe_text(value: str | None, *, fallback: str) -> str:
    if not value:
        return fallback
    compact = " ".join(value.strip().split())
    return compact or fallback


def _track_name(path: str | None) -> str:
    if not path:
        return "Unknown Track"
    return path.split("/")[-1].split("\\")[-1] or "Unknown Track"


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


def _wobble_offset(level: float, bass: float, frame_index: int) -> int:
    strength = int(round((level * 2.0) + (bass * 2.0)))
    if strength <= 0:
        return 0
    phase = frame_index % 4
    if phase in (0, 3):
        return 0
    return strength if phase == 1 else -strength


def _breathing_pad(level: float) -> int:
    return int(round(max(0.0, min(0.45, level * 0.2)) * 10))


def _glitch_text(text: str, seed: int, enabled: bool) -> str:
    if not enabled or not text:
        return text
    chars = list(text)
    swaps = min(2, max(1, len(chars) // 16))
    for offset in range(swaps):
        idx = (seed + (offset * 7)) % len(chars)
        if chars[idx].isspace():
            continue
        glyph = _GLITCH_GLYPHS[(seed + idx + offset) % len(_GLITCH_GLYPHS)]
        chars[idx] = glyph
    return "".join(chars)


def _centered(text: str, width: int, *, wobble: int = 0) -> str:
    stripped = _strip_sgr(text)
    if len(stripped) >= width:
        return _pad_line(text, width)
    available = max(0, width - len(stripped))
    left = max(0, (available // 2) + wobble)
    if left > available:
        left = available
    right = max(0, available - left)
    return (" " * left) + text + (" " * right)


def _apply_shimmer(text: str, high_energy: float, beat_onset: bool) -> str:
    if high_energy < 0.45 and not beat_onset:
        return text
    tint = "\x1b[38;2;53;230;138m"
    if high_energy >= 0.75:
        tint = "\x1b[38;2;242;201;76m"
    if beat_onset:
        tint = "\x1b[38;2;255;90;54m"
    reset = "\x1b[0m"
    stripped = _strip_sgr(text)
    if not stripped.strip():
        return text
    return f"{tint}{text}{reset}"


def _fit_lines(lines: list[str], width: int, height: int) -> str:
    clipped = [_pad_line(line, width) for line in lines[:height]]
    while len(clipped) < height:
        clipped.append(" " * width)
    return "\n".join(clipped)


def _pad_plain(text: str, width: int) -> str:
    if len(text) > width:
        return text[:width]
    if len(text) < width:
        return text + (" " * (width - len(text)))
    return text


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
