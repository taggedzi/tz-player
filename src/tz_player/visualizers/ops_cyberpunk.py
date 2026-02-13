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

_STAGE_COMMANDS: dict[str, tuple[str, ...]] = {
    "SURVEILLANCE": (
        "simscope survey --target track://current --passive",
        "simscope map-signal --window 8s --no-write",
        "simscope fingerprint --artist --album --tempo-est",
    ),
    "VULN SCAN": (
        "simscan seam-check --profile media-pipeline",
        "simscan trust-edges --mode readonly",
        "simscan enumerate soft-lattice --depth 3",
    ),
    "ICE BREAK": (
        "mockice handshake --cipher neon-aes --dry-run",
        "mockice bypass --defense lattice.v9 --simulate",
        "mockice stabilize --channel ghostline",
    ),
    "ACCOUNT TARGET": (
        "simid graph-query --subject track-operator",
        "simid pivot --relation producer->publisher",
        "simid rank-targets --confidence auto",
    ),
    "PRIV ESC": (
        "mocksudo request --scope playback.telemetry",
        "mocksudo elevate --token sim-only --ttl 45s",
        "mocksudo verify --capabilities readonly+analyze",
    ),
    "DATA ACQ": (
        "simgrab index --artifact audio.frames --delta",
        "simgrab acquire --chunks 24 --throttle smart",
        "simgrab seal --stream memory://shadow-cache",
    ),
    "DECRYPT": (
        "mockcrypt derive-key --source metadata.hash",
        "mockcrypt decode --payload frame.bundle --safe",
        "mockcrypt validate --integrity checksum",
    ),
    "DOWNLOAD": (
        "simxfer stage --target /tmp/ops-cache --atomic",
        "simxfer mirror --stream gridlink --compress",
        "simxfer finalize --policy ephemeral",
    ),
    "LOG SCRUB": (
        "simlog scrub --scope local-session --pattern trace",
        "simlog compact --channel ghostline --safe",
        "simlog verify-clean --report summary",
    ),
}

_FEEDBACK: tuple[str, ...] = (
    "[ok] synthetic probe acknowledged",
    "[ok] telemetry packet merged",
    "[ok] checksum stable",
    "[ok] no persistent writes performed",
    "[warn] entropy spike normalized",
    "[ok] simulated boundary maintained",
    "[ok] trace noise reduced",
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
        lines = _build_transcript(
            width=width,
            height=height,
            tick=tick,
            stage_name=stage_name,
            stage_detail=stage_detail,
            stage_pct=stage_pct,
            title=title,
            artist=artist,
            album=album,
            status=status,
            position=position,
            duration=duration,
            volume=int(frame.volume),
            speed=frame.speed,
            repeat_mode=repeat_mode,
            shuffle=shuffle,
            playback_active=frame.status in {"playing", "paused"},
        )

        if self._ansi_enabled:
            lines = [_colorize_line(line) for line in lines]

        return _fit_lines(lines, width, height)


def _sparkline(tick: int, width: int) -> str:
    chart_width = max(8, min(width - 4, 48))
    blocks = " ▁▂▃▄▅▆▇█"
    chars = []
    for idx in range(chart_width):
        level = ((tick // 2) + (idx * 7)) % (len(blocks) - 1)
        chars.append(blocks[level + 1])
    return "SIG " + "".join(chars)


def _fit_lines(lines: list[str], width: int, height: int) -> str:
    clipped = [line[:width] for line in lines[:height]]
    while len(clipped) < height:
        clipped.append(" " * min(width, 1))
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


def _colorize_line(line: str) -> str:
    if line.startswith("[SIMULATION]"):
        return f"\x1b[1;38;2;242;201;76m{line}\x1b[0m"
    if line.startswith("STAGE:"):
        return f"\x1b[1;38;2;53;230;138m{line}\x1b[0m"
    if line.startswith("ops@nightcity:~$"):
        return f"\x1b[1;38;2;0;215;230m{line}\x1b[0m"
    if line.startswith("[ok]"):
        return f"\x1b[38;2;53;230;138m{line}\x1b[0m"
    if line.startswith("[warn]"):
        return f"\x1b[38;2;242;201;76m{line}\x1b[0m"
    if line.startswith(">>") or line.startswith("SIG "):
        return f"\x1b[38;2;0;215;230m{line}\x1b[0m"
    return f"\x1b[38;2;199;208;217m{line}\x1b[0m"


def _build_transcript(
    *,
    width: int,
    height: int,
    tick: int,
    stage_name: str,
    stage_detail: str,
    stage_pct: int,
    title: str,
    artist: str,
    album: str,
    status: str,
    position: str,
    duration: str,
    volume: int,
    speed: float,
    repeat_mode: str,
    shuffle: str,
    playback_active: bool,
) -> list[str]:
    lines: list[str] = [
        "[SIMULATION] CYBER OPS CONSOLE // NON-OPERATIONAL",
        f"TARGET: {title} :: {artist}",
        f"ALBUM: {album} | STATUS: {status}",
        f"STAGE: {stage_name} [{stage_pct:03d}%]  // {stage_detail}",
        (
            f"TIMECODE {position}/{duration} | VOL {volume:03d} | "
            f"SPD {speed:.2f}x | RPT {repeat_mode} | SHUF {shuffle}"
        ),
    ]

    if not playback_active:
        lines.append(">> awaiting active playback stream...")

    commands = _STAGE_COMMANDS.get(stage_name, ("simctl noop --safe",))
    body_target = max(0, height - 2 - len(lines))
    for idx in range(body_target):
        cmd = commands[(tick + idx) % len(commands)]
        line_kind = idx % 3
        if line_kind == 0:
            lines.append(f"ops@nightcity:~$ {cmd}")
        elif line_kind == 1:
            lines.append(_FEEDBACK[(tick + idx) % len(_FEEDBACK)])
        else:
            lines.append(_sparkline(tick + idx, width))
    return lines
