"""Fictional cyberpunk terminal-ops visualizer."""

from __future__ import annotations

from dataclasses import dataclass

from .base import VisualizerContext, VisualizerFrameInput

_STAGES: tuple[tuple[str, str], ...] = (
    ("SURVEILLANCE", "mapping target signal envelope"),
    ("VULN SCAN", "enumerating soft-edge protocol seams"),
    ("ICE BREAK", "simulating defensive lattice bypass"),
    ("ACCOUNT TARGET", "profiling synthetic identity graph"),
    ("PRIV ESC", "elevating mock operator context"),
    ("DATA ACQ", "indexing tagged media artifact blocks"),
    ("DECRYPT", "resolving obfuscated frame payloads"),
    ("DOWNLOAD", "staging packet mirror to local cache"),
    ("LOG SCRUB", "scrubbing trace signatures from sim logs"),
)


@dataclass
class CyberpunkOpsVisualizer:
    plugin_id: str = "ops.cyberpunk"
    display_name: str = "Cyberpunk Ops (Fictional)"
    _ansi_enabled: bool = True
    _stage_ticks: int = 18

    def on_activate(self, context: VisualizerContext) -> None:
        self._ansi_enabled = context.ansi_enabled

    def on_deactivate(self) -> None:
        return None

    def render(self, frame: VisualizerFrameInput) -> str:
        width = max(1, frame.width)
        height = max(1, frame.height)
        tick = max(0, frame.frame_index)
        stage_index = (tick // self._stage_ticks) % len(_STAGES)
        stage_name, stage_detail = _STAGES[stage_index]
        stage_tick = tick % self._stage_ticks
        stage_pct = int(round(((stage_tick + 1) / self._stage_ticks) * 100))

        title = frame.title or _basename(frame.track_path) or "UNNAMED_TRACK"
        artist = frame.artist or "UNKNOWN_ARTIST"
        album = frame.album or "UNKNOWN_ALBUM"
        duration = _duration_text(frame.duration_s)
        position = _position_text(frame.position_s)
        status = frame.status.upper()
        repeat_mode = frame.repeat_mode.upper()
        shuffle = "ON" if frame.shuffle else "OFF"

        lines = [
            "[SIMULATION] CYBER OPS CONSOLE // NON-OPERATIONAL",
            f"TARGET: {title} :: {artist}",
            f"ALBUM: {album} | STATUS: {status}",
            f"STAGE: {stage_name} [{stage_pct:03d}%]",
            f">> {stage_detail}",
            f"TIMECODE {position} / {duration} | VOL {int(frame.volume):03d}",
            f"SPEED {frame.speed:.2f}x | REPEAT {repeat_mode} | SHUFFLE {shuffle}",
            _sparkline(tick, width),
        ]

        if frame.status not in {"playing", "paused"}:
            lines.insert(4, ">> awaiting active playback stream...")

        if self._ansi_enabled:
            lines = [_colorize_line(index, line) for index, line in enumerate(lines)]

        return _fit_lines(lines, width, height)


def _sparkline(tick: int, width: int) -> str:
    chart_width = max(8, min(width - 4, 36))
    blocks = " ▁▂▃▄▅▆▇█"
    chars = []
    for idx in range(chart_width):
        level = ((tick // 2) + (idx * 7)) % (len(blocks) - 1)
        chars.append(blocks[level + 1])
    return "SIG " + "".join(chars)


def _fit_lines(lines: list[str], width: int, height: int) -> str:
    clipped = [line[:width] for line in lines[:height]]
    return "\n".join(clipped)


def _basename(track_path: str | None) -> str | None:
    if not track_path:
        return None
    return track_path.split("/")[-1].split("\\")[-1]


def _duration_text(duration_s: float | None) -> str:
    if duration_s is None or duration_s <= 0:
        return "--:--"
    total = int(duration_s)
    mins, secs = divmod(total, 60)
    return f"{mins:02d}:{secs:02d}"


def _position_text(position_s: float) -> str:
    total = max(0, int(position_s))
    mins, secs = divmod(total, 60)
    return f"{mins:02d}:{secs:02d}"


def _colorize_line(index: int, line: str) -> str:
    if index == 0:
        return f"\x1b[1;38;2;242;201;76m{line}\x1b[0m"
    if index == 3:
        return f"\x1b[1;38;2;53;230;138m{line}\x1b[0m"
    if index in {4, 5, 6, 7}:
        return f"\x1b[38;2;0;215;230m{line}\x1b[0m"
    return f"\x1b[38;2;199;208;217m{line}\x1b[0m"
