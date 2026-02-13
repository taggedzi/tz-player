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

_STAGE_MODES: dict[str, tuple[str, ...]] = {
    "SURVEILLANCE": ("defrag", "mesh", "fingerprint"),
    "VULN SCAN": ("mesh", "entropy", "hash"),
    "ICE BREAK": ("entropy", "hash", "decrypt"),
    "ACCOUNT TARGET": ("graph", "mesh", "hash"),
    "PRIV ESC": ("ladder", "hash", "ladder"),
    "DATA ACQ": ("capture", "defrag", "capture"),
    "DECRYPT": ("entropy", "decrypt", "hash"),
    "DOWNLOAD": ("defrag", "capture", "defrag"),
    "LOG SCRUB": ("defrag", "mesh", "hash"),
}

_PROMPT = "ops@nightcity:~$"


@dataclass
class CyberpunkOpsVisualizer:
    plugin_id: str = "ops.cyberpunk"
    display_name: str = "Cyberpunk Ops (Fictional)"
    _ansi_enabled: bool = True
    _command_ticks: int = 24

    def on_activate(self, context: VisualizerContext) -> None:
        self._ansi_enabled = context.ansi_enabled

    def on_deactivate(self) -> None:
        return None

    def render(self, frame: VisualizerFrameInput) -> str:
        width = max(1, frame.width)
        height = max(1, frame.height)
        tick = max(0, frame.frame_index)
        commands_per_stage = max(len(cmds) for cmds in _STAGE_COMMANDS.values())
        stage_ticks = self._command_ticks * commands_per_stage
        stage_index = (tick // stage_ticks) % len(_STAGES)
        stage_name, stage_detail = _STAGES[stage_index]
        stage_tick = tick % stage_ticks
        stage_pct = int(round(((stage_tick + 1) / stage_ticks) * 100))

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
            command_ticks=self._command_ticks,
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
    if line.startswith(_PROMPT):
        return f"\x1b[1;38;2;0;215;230m{line}\x1b[0m"
    if line.startswith("[ok]"):
        return f"\x1b[38;2;53;230;138m{line}\x1b[0m"
    if line.startswith("[warn]"):
        return f"\x1b[38;2;242;201;76m{line}\x1b[0m"
    if line.startswith("[run]") or line.startswith("[mini]"):
        return f"\x1b[38;2;0;215;230m{line}\x1b[0m"
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
    command_ticks: int,
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
    modes = _STAGE_MODES.get(stage_name, tuple("mesh" for _ in commands))
    stage_ticks = command_ticks * len(commands)
    stage_tick = tick % stage_ticks
    command_idx = min(stage_tick // command_ticks, len(commands) - 1)
    command_tick = stage_tick % command_ticks

    lines.append(
        f"[run] command {command_idx + 1}/{len(commands)} | tick {command_tick + 1}/{command_ticks}"
    )

    for idx in range(command_idx):
        mode = modes[idx] if idx < len(modes) else "mesh"
        command = commands[idx]
        lines.append(f"{_PROMPT} {command}")
        lines.append(f"[ok] {_result_line(stage_name, mode, idx)}")

    active_command = commands[command_idx]
    active_mode = modes[command_idx] if command_idx < len(modes) else "mesh"
    lines.extend(
        _render_active_command(
            command=active_command,
            mode=active_mode,
            stage_name=stage_name,
            command_idx=command_idx,
            command_tick=command_tick,
            command_ticks=command_ticks,
            width=width,
        )
    )

    body_target = max(0, height - len(lines))
    for idx in range(body_target):
        if idx % 2 == 0:
            lines.append(_FEEDBACK[(tick + idx) % len(_FEEDBACK)])
        else:
            lines.append(_sparkline(tick + idx, width))
    return lines


def _render_active_command(
    *,
    command: str,
    mode: str,
    stage_name: str,
    command_idx: int,
    command_tick: int,
    command_ticks: int,
    width: int,
) -> list[str]:
    launch_ticks = 3
    result_ticks = 4
    run_ticks = max(1, command_ticks - launch_ticks - result_ticks)
    lines = [f"{_PROMPT} {command}"]
    if command_tick < launch_ticks:
        lines.append("[run] spawning isolated simulation shell")
        lines.append("[run] attaching dry-run telemetry stream")
        lines.append("[mini] preflight checks passed")
        return lines

    if command_tick < launch_ticks + run_ticks:
        progress_tick = command_tick - launch_ticks
        progress_pct = int(round(((progress_tick + 1) / run_ticks) * 100))
        lines.append(f"[run] {stage_name} task active ({progress_pct:03d}%)")
        lines.extend(_mini_game_lines(mode, progress_tick, run_ticks, width))
        return lines

    lines.append("[run] finalizing task and writing simulated report")
    lines.append(f"[ok] {_result_line(stage_name, mode, command_idx)}")
    lines.append("[ok] command complete; queue advancing")
    return lines


def _mini_game_lines(mode: str, tick: int, run_ticks: int, width: int) -> list[str]:
    if mode == "defrag":
        return _defrag_lines(tick, run_ticks, width)
    if mode == "entropy":
        return _entropy_lines(tick, run_ticks, width)
    if mode == "hash":
        return _hash_lines(tick, run_ticks, width)
    if mode == "decrypt":
        return _decrypt_lines(tick, run_ticks, width)
    if mode == "capture":
        return _capture_lines(tick, run_ticks, width)
    if mode == "ladder":
        return _ladder_lines(tick, run_ticks)
    if mode == "graph":
        return _graph_lines(tick, run_ticks, width)
    return _mesh_lines(tick, run_ticks, width)


def _defrag_lines(tick: int, run_ticks: int, width: int) -> list[str]:
    cells = max(12, min(width - 20, 40))
    filled = int(((tick + 1) / run_ticks) * cells)
    bar = ("#" * filled).ljust(cells, ".")
    head = min(cells - 1, filled)
    cursor = (" " * head) + "^"
    return [
        "[mini] virtual cluster defrag map",
        f"blk[{bar}]",
        f"pos {cursor}",
    ]


def _entropy_lines(tick: int, run_ticks: int, width: int) -> list[str]:
    chunks = max(8, min(width - 24, 32))
    live = int(((tick + 1) / run_ticks) * chunks)
    pool = ("*" * live).ljust(chunks, "-")
    seed = (tick * 73 + 19) % 65536
    return [
        "[mini] entropy furnace feeding key material",
        f"pool[{pool}]",
        f"seed 0x{seed:04x} | jitter {(tick * 13) % 97:02d}ms",
    ]


def _hash_lines(tick: int, run_ticks: int, width: int) -> list[str]:
    attempts = (tick + 1) * 4096
    phase = int(((tick + 1) / run_ticks) * 100)
    sample = f"{(tick * 41) % 10}{(tick * 29) % 10}{(tick * 17) % 10}"
    window = max(8, min(width - 28, 28))
    trail = ("=" * (phase * window // 100)).ljust(window, "-")
    return [
        "[mini] hash cracking arena (simulation)",
        f"try[{trail}] {phase:03d}%",
        f"attempts={attempts} candidate=*{sample}* status=analyzing",
    ]


def _decrypt_lines(tick: int, run_ticks: int, width: int) -> list[str]:
    cols = max(6, min((width - 12) // 2, 16))
    unlock = int(((tick + 1) / run_ticks) * cols)
    locked = cols - unlock
    panel = ("UU " * unlock) + ("[] " * locked)
    return [
        "[mini] block cipher lane decode",
        panel.strip(),
        f"lanes unlocked={unlock:02d}/{cols:02d}",
    ]


def _capture_lines(tick: int, run_ticks: int, width: int) -> list[str]:
    packets = 18 + tick * 3
    dropped = (tick * 7) % 3
    rate = 32 + (tick * 5) % 60
    packet_span = max(10, min(width - 20, 34))
    graph = (">" * ((tick % packet_span) + 1)).ljust(packet_span, ".")
    return [
        "[mini] packet capture mirror stream",
        f"rx[{graph}]",
        f"pkts={packets:04d} drop={dropped} rate={rate:03d}kB/s",
    ]


def _ladder_lines(tick: int, run_ticks: int) -> list[str]:
    steps = ("guest", "operator", "maint", "elevated", "audit-root")
    reached = min(len(steps) - 1, int(((tick + 1) / run_ticks) * len(steps)))
    ladder = " -> ".join(
        f"[{name}]" if idx <= reached else name for idx, name in enumerate(steps)
    )
    return [
        "[mini] privilege ladder simulation",
        ladder,
        f"token horizon {(tick * 9) % 61:02d}s",
    ]


def _graph_lines(tick: int, run_ticks: int, width: int) -> list[str]:
    nodes = max(6, min((width - 16) // 4, 12))
    hot = (tick % nodes) + 1
    map_line = " ".join("@" if idx < hot else "o" for idx in range(nodes))
    edges = nodes + hot * 2
    return [
        "[mini] identity graph pivot",
        f"nodes {map_line}",
        f"resolved edges={edges:03d} confidence={(55 + tick * 3) % 100:02d}%",
    ]


def _mesh_lines(tick: int, run_ticks: int, width: int) -> list[str]:
    nodes = max(8, min(width - 26, 28))
    sweep = tick % nodes
    mesh = "".join("X" if idx == sweep else "." for idx in range(nodes))
    return [
        "[mini] net mesh sweep",
        f"mesh[{mesh}]",
        f"scan_index={sweep:02d} saturation={(tick * 11) % 100:02d}%",
    ]


def _result_line(stage_name: str, mode: str, command_idx: int) -> str:
    if mode == "defrag":
        return f"{stage_name.lower()} map compacted; segment table stable"
    if mode == "entropy":
        return f"{stage_name.lower()} entropy buffer reached target threshold"
    if mode == "hash":
        return f"{stage_name.lower()} hash pattern scored; no live exploit path"
    if mode == "decrypt":
        return f"{stage_name.lower()} payload decoded into synthetic report set"
    if mode == "capture":
        return f"{stage_name.lower()} packet mirror sealed to ephemeral cache"
    if mode == "ladder":
        return f"{stage_name.lower()} privilege chain verified in simulation"
    if mode == "graph":
        return f"{stage_name.lower()} identity graph correlated with metadata tags"
    return f"{stage_name.lower()} mesh scan complete; seam index={command_idx + 1:02d}"
