"""Beat diagnostics visualizer for validating onset and beat-strength behavior."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .base import VisualizerContext, VisualizerFrameInput

_SGR_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


@dataclass
class BeatScopeVisualizer:
    """Render beat-debug telemetry with obvious beat pulse feedback."""

    plugin_id: str = "viz.debug.beat_scope"
    display_name: str = "Beat Scope (Debug)"
    plugin_api_version: int = 1
    requires_beat: bool = True
    _ansi_enabled: bool = True
    _track_key: str = ""
    _flash_frames: int = 0
    _onset_history: list[bool] = field(default_factory=list)

    def on_activate(self, context: VisualizerContext) -> None:
        self._ansi_enabled = context.ansi_enabled
        self._flash_frames = 0
        self._onset_history.clear()

    def on_deactivate(self) -> None:
        self._flash_frames = 0
        self._onset_history.clear()

    def render(self, frame: VisualizerFrameInput) -> str:
        width = max(1, frame.width)
        height = max(1, frame.height)
        onset = bool(frame.beat_is_onset)
        strength = max(0.0, min(1.0, float(frame.beat_strength or 0.0)))
        track_key = frame.track_path or frame.title or ""
        if track_key != self._track_key:
            self._track_key = track_key
            self._flash_frames = 0
            self._onset_history.clear()

        if onset:
            self._flash_frames = 4
        elif self._flash_frames > 0:
            self._flash_frames -= 1

        history_len = max(8, width - 14)
        self._onset_history.append(onset)
        if len(self._onset_history) > history_len:
            self._onset_history = self._onset_history[-history_len:]

        lines = [
            "BEAT SCOPE (DEBUG)",
            _status_line(frame, onset=onset, strength=strength),
            _strength_line(
                width=width, strength=strength, ansi_enabled=self._ansi_enabled
            ),
            _history_line(
                width=width,
                history=self._onset_history,
                ansi_enabled=self._ansi_enabled,
            ),
        ]
        rows = max(0, height - len(lines))
        lines.extend(
            _pulse_rows(
                rows=rows,
                width=width,
                flash_frames=self._flash_frames,
                strength=strength,
                ansi_enabled=self._ansi_enabled,
            )
        )
        return _fit_lines(lines, width, height)


def _status_line(frame: VisualizerFrameInput, *, onset: bool, strength: float) -> str:
    beat = "ONSET" if onset else "IDLE "
    bpm = (
        f"{frame.beat_bpm:5.1f}"
        if frame.beat_bpm is not None and frame.beat_bpm > 0
        else "  n/a"
    )
    source = (frame.beat_source or "missing").upper()
    status = (frame.beat_status or "missing").upper()
    return (
        f"BEAT {beat} | STRENGTH {int(round(strength * 100)):3d}% | "
        f"BPM {bpm} | SRC {source} | {status}"
    )


def _strength_line(*, width: int, strength: float, ansi_enabled: bool) -> str:
    bar_width = max(8, width - 20)
    filled = int(round(bar_width * strength))
    raw = f"{'#' * filled}{'.' * (bar_width - filled)}"
    if ansi_enabled:
        bar = "".join(_color_strength(ch, strength=strength) for ch in raw)
    else:
        bar = raw
    return f"STRENGTH [{bar}]"


def _history_line(*, width: int, history: list[bool], ansi_enabled: bool) -> str:
    history_width = max(8, width - 10)
    recent = history[-history_width:]
    raw = "".join("|" if hit else "." for hit in recent).rjust(history_width, ".")
    graph = "".join(_color_history(ch) for ch in raw) if ansi_enabled else raw
    return f"ONSETS [{graph}]"


def _pulse_rows(
    *,
    rows: int,
    width: int,
    flash_frames: int,
    strength: float,
    ansi_enabled: bool,
) -> list[str]:
    if rows <= 0:
        return []
    lines: list[str] = []
    pulse_width = max(1, int(round(strength * width)))
    for row_idx in range(rows):
        if flash_frames > 0:
            glyph = "!" if row_idx % 2 == 0 else "#"
            base = (glyph * width)[:width]
            if ansi_enabled:
                lines.append(_color_pulse(base, flash_frames=flash_frames))
            else:
                lines.append(base)
            continue
        base = ("=" * pulse_width).ljust(width, " ")
        if ansi_enabled:
            lines.append(_color_idle(base))
        else:
            lines.append(base)
    return lines


def _color_strength(glyph: str, *, strength: float) -> str:
    if glyph == ".":
        return f"\x1b[38;2;70;80;96m{glyph}\x1b[0m"
    if strength >= 0.70:
        return f"\x1b[38;2;255;98;66m{glyph}\x1b[0m"
    if strength >= 0.40:
        return f"\x1b[38;2;255;198;66m{glyph}\x1b[0m"
    return f"\x1b[38;2;112;224;154m{glyph}\x1b[0m"


def _color_history(glyph: str) -> str:
    if glyph == "|":
        return f"\x1b[38;2;255;225;120m{glyph}\x1b[0m"
    return f"\x1b[38;2;90;96;120m{glyph}\x1b[0m"


def _color_pulse(text: str, *, flash_frames: int) -> str:
    if flash_frames >= 3:
        return f"\x1b[38;2;255;82;82m{text}\x1b[0m"
    return f"\x1b[38;2;255;176;66m{text}\x1b[0m"


def _color_idle(text: str) -> str:
    if not text.strip():
        return text
    prefix = len(text) - len(text.lstrip(" "))
    filled = text[prefix:]
    return (" " * prefix) + f"\x1b[38;2;106;210;255m{filled}\x1b[0m" if filled else text


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
