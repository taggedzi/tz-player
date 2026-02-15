"""HackScope-style fictional terminal visualizer."""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass
from hashlib import sha256

from .base import VisualizerContext, VisualizerFrameInput

_SGR_PATTERN = re.compile(r"\x1b\[[0-9;]*m")
_ANSI_RESET = "\x1b[0m"
_ANSI_DIM = "\x1b[2m"
_ANSI_CYAN = "\x1b[36m"
_ANSI_GREEN = "\x1b[32m"
_ANSI_YELLOW = "\x1b[33m"
_ANSI_MAGENTA = "\x1b[35m"
_ANSI_BRIGHT_YELLOW = "\x1b[93m"

_PHASES: tuple[tuple[str, int], ...] = (
    ("BOOT", 24),
    ("ICE", 60),
    ("MAP", 45),
    ("DEFRAG", 42),
    ("SCAN", 36),
    ("DECRYPT", 60),
    ("EXTRACT", 39),
    ("COVER", 33),
    ("DOSSIER", 45),
)
_TOTAL_PHASE_FRAMES = sum(count for _name, count in _PHASES)


@dataclass
class HackScopeVisualizer:
    plugin_id: str = "ops.hackscope"
    display_name: str = "HackScope (Fictional)"
    _ansi_enabled: bool = True

    def on_activate(self, context: VisualizerContext) -> None:
        self._ansi_enabled = context.ansi_enabled

    def on_deactivate(self) -> None:
        return None

    def render(self, frame: VisualizerFrameInput) -> str:
        width = max(1, frame.width)
        height = max(1, frame.height)
        track_path = frame.track_path or ""
        seed = _stable_seed(track_path or frame.title or "hackscope")
        stage_id = f"{seed:08x}"

        if frame.status not in {"playing", "paused"}:
            base = _render_idle(
                stage_id,
                title=frame.title or _basename(track_path) or "Unknown",
                artist=frame.artist or "Unknown",
                width=width,
                height=height,
                local_i=frame.frame_index,
                use_ansi=self._ansi_enabled,
            )
            return _apply_ambient(
                base, width, height, seed, frame.frame_index, self._ansi_enabled
            )

        phase_name, local_i, phase_len = _locate_phase(
            frame.frame_index % _TOTAL_PHASE_FRAMES
        )
        fields = {
            "title": frame.title or _basename(track_path) or "Unknown",
            "artist": frame.artist or "Unknown",
            "album": frame.album or "Unknown",
            "duration": _duration_text(frame.duration_s),
            "position": _duration_text(frame.position_s),
            "speed": f"{frame.speed:.2f}x",
            "volume": f"{int(frame.volume):03d}",
        }

        if phase_name == "BOOT":
            base = _render_boot(
                stage_id, width, height, local_i, phase_len, self._ansi_enabled
            )
        elif phase_name == "ICE":
            base = _render_ice(
                stage_id,
                fields,
                width,
                height,
                seed,
                local_i,
                phase_len,
                self._ansi_enabled,
            )
        elif phase_name == "MAP":
            base = _render_map(
                stage_id,
                fields,
                width,
                height,
                seed,
                local_i,
                phase_len,
                self._ansi_enabled,
            )
        elif phase_name == "DEFRAG":
            base = _render_defrag(
                stage_id, width, height, seed, local_i, phase_len, self._ansi_enabled
            )
        elif phase_name == "SCAN":
            base = _render_scan(
                stage_id,
                fields,
                width,
                height,
                seed,
                local_i,
                phase_len,
                self._ansi_enabled,
            )
        elif phase_name == "DECRYPT":
            base = _render_decrypt(
                stage_id,
                fields,
                width,
                height,
                seed,
                local_i,
                phase_len,
                self._ansi_enabled,
            )
        elif phase_name == "EXTRACT":
            base = _render_extract(
                stage_id,
                fields,
                width,
                height,
                seed,
                local_i,
                phase_len,
                self._ansi_enabled,
            )
        elif phase_name == "COVER":
            base = _render_cover(
                stage_id,
                fields,
                width,
                height,
                seed,
                local_i,
                phase_len,
                self._ansi_enabled,
            )
        else:
            base = _render_dossier(stage_id, fields, width, height, self._ansi_enabled)

        return _apply_ambient(
            base, width, height, seed, frame.frame_index, self._ansi_enabled
        )


def _stable_seed(value: str) -> int:
    digest = sha256(value.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _locate_phase(global_frame: int) -> tuple[str, int, int]:
    remaining = max(0, int(global_frame))
    for name, count in _PHASES:
        if remaining < count:
            return name, remaining, count
        remaining -= count
    last_name, last_count = _PHASES[-1]
    return last_name, last_count - 1, last_count


def _duration_text(seconds: float | None) -> str:
    if seconds is None or not math.isfinite(seconds):
        return "Unknown"
    value = max(0, int(seconds))
    mins, secs = divmod(value, 60)
    return f"{mins:02d}:{secs:02d}"


def _basename(path: str) -> str:
    return path.split("/")[-1].split("\\")[-1]


def _render_boot(
    stage_id: str, width: int, height: int, local_i: int, phase_len: int, use_ansi: bool
) -> str:
    lines = [
        f"{_c('[HackScope]', _ANSI_CYAN, use_ansi)} BOOT [{stage_id}]",
        "",
        ">> booting hackscript",
        ">> probing media telemetry",
        ">> preparing visual channels",
    ]
    pct = _pct(local_i, phase_len)
    lines.append("")
    lines.append(
        f"{_c('progress', _ANSI_DIM, use_ansi)}: {pct:3d}% [{_c(_bar(pct, max(10, min(34, width - 20)), '#', '-'), _ANSI_GREEN, use_ansi)}]"
    )
    lines.append(f"{_c('note', _ANSI_DIM, use_ansi)}: fictional terminal simulation")
    return _pad_to_viewport(lines, width, height)


def _render_ice(
    stage_id: str,
    fields: dict[str, str],
    width: int,
    height: int,
    seed: int,
    local_i: int,
    phase_len: int,
    use_ansi: bool,
) -> str:
    left = [
        f"{_c('[HackScope]', _ANSI_CYAN, use_ansi)} BREACH ICE [{stage_id}]",
        "",
        f">> target: {_truth(fields['title'], use_ansi)}",
        f">> artist: {_truth(fields['artist'], use_ansi)}",
        ">> handshake: simulated",
        ">> perimeter: mapped",
        ">> vector: timing skew",
    ]
    pct = _pct(local_i, phase_len)
    right_w = max(8, width // 3 - 2)
    bar = _c(_bar(pct, max(8, right_w - 6), "#", "-"), _ANSI_GREEN, use_ansi)
    right = [
        _c("ICE", _ANSI_CYAN, use_ansi),
        f"{pct:3d}% [{bar}]",
        "",
    ]
    right.extend(
        _lattice(
            seed,
            local_i,
            max(6, min(10, height - 5)),
            max(10, min(18, right_w)),
            use_ansi,
        )
    )
    return _render_two_col(left, right, width, height)


def _render_map(
    stage_id: str,
    fields: dict[str, str],
    width: int,
    height: int,
    seed: int,
    local_i: int,
    phase_len: int,
    use_ansi: bool,
) -> str:
    pct = _pct(local_i, phase_len)
    left = [
        f"{_c('[HackScope]', _ANSI_CYAN, use_ansi)} MAP [{stage_id}]",
        "",
        f">> title: {_truth(fields['title'], use_ansi)}",
        f">> artist: {_truth(fields['artist'], use_ansi)}",
        f">> album: {_truth(fields['album'], use_ansi)}",
        f">> timecode: {_truth(fields['position'], use_ansi)}/{_truth(fields['duration'], use_ansi)}",
    ]
    right_w = max(8, width // 3 - 2)
    bar = _c(_bar(pct, max(8, right_w - 6), "#", "-"), _ANSI_GREEN, use_ansi)
    right = [_c("TOPOLOGY", _ANSI_CYAN, use_ansi), f"{pct:3d}% [{bar}]", ""]
    right.extend(
        _nodes(
            seed,
            local_i,
            max(6, min(10, height - 5)),
            max(10, min(18, right_w)),
            use_ansi,
        )
    )
    return _render_two_col(left, right, width, height)


def _render_defrag(
    stage_id: str,
    width: int,
    height: int,
    seed: int,
    local_i: int,
    phase_len: int,
    use_ansi: bool,
) -> str:
    rng = random.Random((seed ^ (local_i * 0x9E3779B1)) & 0xFFFFFFFF)
    grid_w = max(18, min(48, width - 2))
    grid_h = max(7, min(14, height - 6))
    pct = _pct(local_i, phase_len)
    lines = [f"{_c('[HackScope]', _ANSI_CYAN, use_ansi)} DEFRAG CACHE [{stage_id}]", ""]
    lines.append(
        f"{_c('progress', _ANSI_DIM, use_ansi)}: {pct:3d}% [{_c(_bar(pct, max(10, min(40, width - 18)), '█', ' '), _ANSI_GREEN, use_ansi)}]"
    )
    lines.append("")
    sweep = pct / 100.0
    for _ in range(grid_h):
        row = [
            "·" if rng.random() < 0.55 else ("▒" if rng.random() < 0.7 else "█")
            for _ in range(grid_w)
        ]
        row.sort(
            key=lambda ch: 0 if ch == "█" else (1 if ch == "▒" and sweep < 0.6 else 2)
        )
        lines.append("".join(row))
    lines.append("")
    lines.append(
        f"{_c('note', _ANSI_DIM, use_ansi)}: animation only (no disk activity)"
    )
    return _pad_to_viewport(lines, width, height)


def _render_scan(
    stage_id: str,
    fields: dict[str, str],
    width: int,
    height: int,
    seed: int,
    local_i: int,
    phase_len: int,
    use_ansi: bool,
) -> str:
    del seed
    pct = _pct(local_i, phase_len)
    lines = [
        f"{_c('[HackScope]', _ANSI_CYAN, use_ansi)} SCAN [{stage_id}]",
        "",
        f"{_c('progress', _ANSI_DIM, use_ansi)}: {pct:3d}% [{_c(_bar(pct, max(10, min(40, width - 18)), '█', '░'), _ANSI_GREEN, use_ansi)}]",
        "",
        f">> speed: {_truth(fields['speed'], use_ansi)}",
        f">> volume: {_truth(fields['volume'], use_ansi)}",
        f">> stream: {_truth(fields['position'], use_ansi)}/{_truth(fields['duration'], use_ansi)}",
        ">> scan: stable (simulated)",
        ">> verdict: non-operational effect-only",
    ]
    return _pad_to_viewport(lines, width, height)


def _render_decrypt(
    stage_id: str,
    fields: dict[str, str],
    width: int,
    height: int,
    seed: int,
    local_i: int,
    phase_len: int,
    use_ansi: bool,
) -> str:
    del seed
    pct = _pct(local_i, phase_len)
    lines = [
        f"{_c('[HackScope]', _ANSI_CYAN, use_ansi)} DECRYPT/EXTRACT [{stage_id}]",
        f"{_c('track', _ANSI_DIM, use_ansi)}: {_truth(fields['title'], use_ansi)}",
        "",
        f"{_c('progress', _ANSI_DIM, use_ansi)}: {pct:3d}% [{_c(_bar(pct, max(10, min(40, width - 18)), '█', '░'), _ANSI_GREEN, use_ansi)}]",
        "",
        f">> payload: {_truth(fields['album'], use_ansi)}",
        ">> keyslot: derive (simulated)",
        ">> decrypt: stream start (simulated)",
        ">> extract: pass (simulated)",
    ]
    return _pad_to_viewport(lines, width, height)


def _render_extract(
    stage_id: str,
    fields: dict[str, str],
    width: int,
    height: int,
    seed: int,
    local_i: int,
    phase_len: int,
    use_ansi: bool,
) -> str:
    del seed
    pct = _pct(local_i, phase_len)
    lines = [
        f"{_c('[HackScope]', _ANSI_CYAN, use_ansi)} VERIFY [{stage_id}]",
        "",
        f"{_c('progress', _ANSI_DIM, use_ansi)}: {pct:3d}% [{_c(_bar(pct, max(10, min(40, width - 18)), '█', '░'), _ANSI_GREEN, use_ansi)}]",
        "",
        f">> title: {_truth(fields['title'], use_ansi)}",
        f">> artist: {_truth(fields['artist'], use_ansi)}",
        f">> album: {_truth(fields['album'], use_ansi)}",
        ">> checksum: pass (simulated)",
    ]
    return _pad_to_viewport(lines, width, height)


def _render_cover(
    stage_id: str,
    fields: dict[str, str],
    width: int,
    height: int,
    seed: int,
    local_i: int,
    phase_len: int,
    use_ansi: bool,
) -> str:
    del seed
    pct = _pct(local_i, phase_len)
    lines = [
        f"{_c('[HackScope]', _ANSI_CYAN, use_ansi)} COVER TRACKS [{stage_id}]",
        "",
        f"{_c('redacting', _ANSI_DIM, use_ansi)}: {pct:3d}% [{_c(_bar(pct, max(10, min(40, width - 18)), '=', '-'), _ANSI_MAGENTA, use_ansi)}]",
        "",
        f">> summary: {_truth(fields['title'], use_ansi)}",
        f">> artist: {_truth(fields['artist'], use_ansi)}",
        ">> logs: scrubbed (simulated)",
    ]
    return _pad_to_viewport(lines, width, height)


def _render_dossier(
    stage_id: str, fields: dict[str, str], width: int, height: int, use_ansi: bool
) -> str:
    lines = [
        _c("=== HACKSCRIPT DOSSIER ===", _ANSI_CYAN, use_ansi),
        f"{_c('Session', _ANSI_DIM, use_ansi)} : {_truth(stage_id, use_ansi)}",
        f"{_c('Title', _ANSI_DIM, use_ansi)}   : {_truth(fields['title'], use_ansi)}",
        f"{_c('Artist', _ANSI_DIM, use_ansi)}  : {_truth(fields['artist'], use_ansi)}",
        f"{_c('Album', _ANSI_DIM, use_ansi)}   : {_truth(fields['album'], use_ansi)}",
        f"{_c('Time', _ANSI_DIM, use_ansi)}    : {_truth(fields['position'], use_ansi)}/{_truth(fields['duration'], use_ansi)}",
        f"{_c('Speed', _ANSI_DIM, use_ansi)}   : {_truth(fields['speed'], use_ansi)}",
        f"{_c('Volume', _ANSI_DIM, use_ansi)}  : {_truth(fields['volume'], use_ansi)}",
        "",
        f"{_c('note', _ANSI_DIM, use_ansi)}: fictional display, non-operational",
    ]
    return _pad_to_viewport(lines, width, height)


def _render_idle(
    stage_id: str,
    title: str,
    artist: str,
    width: int,
    height: int,
    local_i: int,
    use_ansi: bool,
) -> str:
    spinner = "|/-\\"
    lines = [
        f"{_c('[HackScope]', _ANSI_CYAN, use_ansi)} IDLE [{stage_id}] {spinner[local_i % len(spinner)]}",
        "",
        f"{_c('now', _ANSI_DIM, use_ansi)}: {_truth(title, use_ansi)}",
        f"{_c('artist', _ANSI_DIM, use_ansi)}: {_truth(artist, use_ansi)}",
        "",
        ">> waiting for active playback stream...",
    ]
    return _pad_to_viewport(lines, width, height)


def _pct(local_i: int, phase_len: int) -> int:
    if phase_len <= 1:
        return 100
    return int((local_i / (phase_len - 1)) * 100)


def _bar(pct: int, width: int, fill: str, empty: str) -> str:
    width = max(1, width)
    pct = max(0, min(100, pct))
    fill_n = int((pct / 100.0) * width)
    return (fill * fill_n) + (empty * (width - fill_n))


def _lattice(seed: int, local_i: int, h: int, w: int, use_ansi: bool) -> list[str]:
    sweep = local_i % max(1, w - 2)
    lines: list[str] = []
    for y in range(h):
        row = []
        for x in range(w):
            if x in (0, w - 1) or y in (0, h - 1):
                row.append("+")
            elif x == 1 + sweep:
                row.append(_c("*", _ANSI_YELLOW, use_ansi))
            else:
                row.append(".")
        lines.append("".join(row))
    return lines


def _nodes(seed: int, local_i: int, h: int, w: int, use_ansi: bool) -> list[str]:
    rng = random.Random((seed ^ 0xA5A5A5A5) & 0xFFFFFFFF)
    coords = [
        (1 + rng.randrange(max(1, w - 2)), 1 + rng.randrange(max(1, h - 2)))
        for _ in range(8)
    ]
    lit = max(1, min(len(coords), 1 + local_i // 3))
    sweep = local_i % max(1, w - 2)
    lines: list[str] = []
    for y in range(h):
        row = []
        for x in range(w):
            if x in (0, w - 1) or y in (0, h - 1):
                row.append("+")
            elif x == 1 + sweep:
                row.append(_c("*", _ANSI_YELLOW, use_ansi))
            elif (x, y) in coords[:lit]:
                row.append(_c("o", _ANSI_MAGENTA, use_ansi))
            else:
                row.append(".")
        lines.append("".join(row))
    return lines


def _truth(value: str, use_ansi: bool) -> str:
    return _c(value, _ANSI_BRIGHT_YELLOW, use_ansi)


def _c(text: str, code: str, enabled: bool) -> str:
    if not enabled:
        return text
    return f"{code}{text}{_ANSI_RESET}"


def _apply_ambient(
    frame: str, width: int, height: int, seed: int, global_frame: int, use_ansi: bool
) -> str:
    ambient = _ambient_lines(width, height, seed, global_frame)
    lines = frame.splitlines()
    while len(lines) < height:
        lines.append("")
    out: list[str] = []
    for idx in range(height):
        out.append(_overlay_ambient(lines[idx], ambient[idx], width, use_ansi))
    return "\n".join(out)


def _ambient_lines(width: int, height: int, seed: int, global_frame: int) -> list[str]:
    rng = random.Random((seed ^ (global_frame * 0x9E3779B1)) & 0xFFFFFFFF)
    density = 0.004
    chars = ".:·"
    out: list[str] = []
    for row in range(height):
        if row == 0:
            out.append(" " * width)
            continue
        line = "".join(
            chars[rng.randrange(len(chars))] if rng.random() < density else " "
            for _ in range(width)
        )
        out.append(line)
    return out


def _overlay_ambient(content: str, ambient: str, width: int, use_ansi: bool) -> str:
    del use_ansi
    out: list[str] = []
    visible = 0
    idx = 0
    while idx < len(content) and visible < width:
        if (
            content[idx] == "\x1b"
            and idx + 1 < len(content)
            and content[idx + 1] == "["
        ):
            end = content.find("m", idx + 2)
            if end != -1:
                out.append(content[idx : end + 1])
                idx = end + 1
                continue
        ch = content[idx]
        idx += 1
        out.append(ambient[visible] if ch == " " else ch)
        visible += 1
    while visible < width:
        out.append(ambient[visible])
        visible += 1
    return "".join(out)


def _pad_to_viewport(lines: list[str], width: int, height: int) -> str:
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


def _render_two_col(left: list[str], right: list[str], width: int, height: int) -> str:
    gutter = 1 if width >= 3 else 0
    split = max(10, (width * 2) // 3)
    left_w = max(1, min(width, split))
    right_w = max(0, width - left_w - gutter)
    out: list[str] = []
    for idx in range(height):
        left_line = _pad_line(left[idx] if idx < len(left) else "", left_w)
        if right_w > 0:
            right_line = _pad_line(right[idx] if idx < len(right) else "", right_w)
            out.append(f"{left_line}{' ' * gutter}{right_line}")
        else:
            out.append(left_line)
    return "\n".join(out)
