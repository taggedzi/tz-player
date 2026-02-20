"""Beat-triggered fireworks visualizer with FFT and level-reactive styling."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from hashlib import sha256

from .base import VisualizerContext, VisualizerFrameInput

_SGR_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


@dataclass
class _Rocket:
    x: float
    y: float
    vx: float
    vy: float
    y_explode: float
    theme: str
    burst_type: str


@dataclass
class _Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    brightness: float
    theme: str
    kind: str


@dataclass
class FireworksVisualizer:
    """Render beat-launched rockets and musical fireworks bursts."""

    plugin_id: str = "viz.particle.fireworks"
    display_name: str = "Beat Fireworks"
    plugin_api_version: int = 1
    requires_spectrum: bool = True
    requires_beat: bool = True
    requires_waveform: bool = True
    _ansi_enabled: bool = True
    _track_key: str = ""
    _rng_state: int = 1
    _last_beat_frame: int = -1
    _last_launch_frame: int = -1
    _rockets: list[_Rocket] = field(default_factory=list)
    _particles: list[_Particle] = field(default_factory=list)

    def on_activate(self, context: VisualizerContext) -> None:
        self._ansi_enabled = context.ansi_enabled
        self._rockets.clear()
        self._particles.clear()

    def on_deactivate(self) -> None:
        self._rockets.clear()
        self._particles.clear()

    def render(self, frame: VisualizerFrameInput) -> str:
        width = max(1, frame.width)
        height = max(1, frame.height)
        field_rows = max(1, height - 2)
        bass, mids, highs = _band_triplet(frame.spectrum_bands)
        vu = _vu_level(frame)
        beat_onset = bool(frame.beat_is_onset)
        crackle = _waveform_roughness(frame, highs)
        theme = _theme_for_bands(bass, mids, highs)

        track_key = _track_key(frame)
        if track_key != self._track_key:
            self._track_key = track_key
            self._rng_state = _stable_seed(track_key)
            self._last_beat_frame = -1
            self._last_launch_frame = -1
            self._rockets.clear()
            self._particles.clear()

        beat_strength = max(0.0, min(1.0, float(frame.beat_strength or 0.0)))
        energy = _launch_energy(vu=vu, bass=bass, mids=mids, highs=highs)
        did_launch = False

        if beat_onset and frame.frame_index != self._last_beat_frame:
            self._last_beat_frame = frame.frame_index
            did_launch = True
            launches = 2 if (vu > 0.74 and (bass > 0.55 or beat_strength > 0.62)) else 1
            for _ in range(launches):
                self._spawn_rocket(
                    width=width, rows=field_rows, bass=bass, theme=theme, high=highs
                )
        elif self._should_auto_launch(
            frame_index=frame.frame_index,
            energy=energy,
            bass=bass,
            highs=highs,
            beat_strength=beat_strength,
        ):
            did_launch = True
            launches = 2 if (energy > 0.86 and (highs > 0.62 or bass > 0.68)) else 1
            for _ in range(launches):
                self._spawn_rocket(
                    width=width, rows=field_rows, bass=bass, theme=theme, high=highs
                )

        if did_launch:
            self._last_launch_frame = frame.frame_index

        self._update_rockets(rows=field_rows, vu=vu, bass=bass, mids=mids, highs=highs)
        self._update_particles(rows=field_rows, cols=width, crackle=crackle)

        canvas = [[" " for _ in range(width)] for _ in range(field_rows)]
        for particle in self._particles:
            px = int(round(particle.x))
            py = int(round(particle.y))
            if 0 <= px < width and 0 <= py < field_rows:
                canvas[py][px] = _particle_glyph(particle.brightness)
        for rocket in self._rockets:
            rx = int(round(rocket.x))
            ry = int(round(rocket.y))
            if 0 <= rx < width and 0 <= ry < field_rows:
                canvas[ry][rx] = "^"
                trail_len = 1 + int(round(vu * 4.0))
                for offset in range(1, trail_len + 1):
                    ty = ry + offset
                    if 0 <= ty < field_rows and canvas[ty][rx] == " ":
                        canvas[ty][rx] = "|"

        lines = [
            "BEAT FIREWORKS",
            _status_line(
                beat_onset=beat_onset,
                did_launch=did_launch,
                theme=theme,
                bass=bass,
                mids=mids,
                highs=highs,
                vu=vu,
            ),
        ]
        lines.extend(_render_rows(canvas, ansi_enabled=self._ansi_enabled))
        return _fit_lines(lines, width, height)

    def _spawn_rocket(
        self, *, width: int, rows: int, bass: float, theme: str, high: float
    ) -> None:
        margin = max(2, int(width * 0.12))
        min_x = margin
        max_x = max(min_x + 1, width - margin - 1)
        x = float(min_x + self._rand_int(max_x - min_x + 1))
        vx = (self._rand_float() - 0.5) * 0.45
        vy = -(1.05 + self._rand_float() * 0.55)
        min_h = max(3.0, rows * 0.25)
        max_h = max(min_h + 1.0, rows * 0.72)
        # More bass tends to explode lower (heavier feel).
        explode_height = min_h + (1.0 - bass) * (max_h - min_h)
        y_explode = max(2.0, rows - explode_height)
        burst_type = _burst_type_for_bands(bass=bass, high=high, rng=self._rand_float())
        self._rockets.append(
            _Rocket(
                x=x,
                y=float(rows - 1),
                vx=vx,
                vy=vy,
                y_explode=y_explode,
                theme=theme,
                burst_type=burst_type,
            )
        )
        self._rockets = self._rockets[-6:]

    def _update_rockets(
        self, *, rows: int, vu: float, bass: float, mids: float, highs: float
    ) -> None:
        next_rockets: list[_Rocket] = []
        for rocket in self._rockets:
            rocket.x += rocket.vx
            rocket.y += rocket.vy
            rocket.vy += 0.015
            if rocket.y <= rocket.y_explode:
                self._explode(
                    rocket=rocket,
                    vu=vu,
                    bass=bass,
                    mids=mids,
                    highs=highs,
                )
                continue
            if -1.0 <= rocket.y < rows + 1.0:
                next_rockets.append(rocket)
        self._rockets = next_rockets

    def _explode(
        self, *, rocket: _Rocket, vu: float, bass: float, mids: float, highs: float
    ) -> None:
        base_count = 24 + int(round(vu * 36))
        if rocket.burst_type == "ring":
            base_count = int(base_count * 0.85)
        elif rocket.burst_type == "palm":
            base_count = int(base_count * 0.75)
        elif rocket.burst_type == "willow":
            base_count = int(base_count * 1.15)
        count = max(16, min(110, base_count))
        speed_scale = 0.65 + (mids * 0.55)
        spike = _spike_ratio(
            rocket_theme=rocket.theme, bass=bass, mids=mids, highs=highs
        )
        crackle_count = 0
        if spike > 2.2:
            crackle_count = 6 + int(round((spike - 2.2) * 10))

        if rocket.burst_type == "palm":
            arms = 6 + self._rand_int(5)
            for arm in range(arms):
                angle = (2.0 * math.pi * arm) / arms
                for step in range(max(2, count // arms)):
                    jitter = (self._rand_float() - 0.5) * 0.2
                    speed = speed_scale * (0.55 + step * 0.16)
                    self._particles.append(
                        _Particle(
                            x=rocket.x,
                            y=rocket.y,
                            vx=math.cos(angle + jitter) * speed,
                            vy=math.sin(angle + jitter) * speed * 0.56,
                            life=1.0,
                            brightness=1.0,
                            theme=rocket.theme,
                            kind="main",
                        )
                    )
        else:
            for idx in range(count):
                angle = (2.0 * math.pi * idx) / count
                if rocket.burst_type == "ring":
                    offset = 0.8
                else:
                    offset = (
                        self._rand_float()
                        if rocket.burst_type == "chrysanthemum"
                        else self._rand_float() ** 0.4
                    )
                speed = speed_scale * (0.55 + offset * 1.25)
                if rocket.burst_type == "willow":
                    speed *= 0.75
                self._particles.append(
                    _Particle(
                        x=rocket.x,
                        y=rocket.y,
                        vx=math.cos(angle) * speed,
                        vy=math.sin(angle) * speed * 0.56,
                        life=1.0,
                        brightness=1.0,
                        theme=rocket.theme,
                        kind="main",
                    )
                )

        for _ in range(max(0, min(40, crackle_count))):
            angle = self._rand_float() * (2.0 * math.pi)
            speed = 0.35 + self._rand_float() * 0.85
            self._particles.append(
                _Particle(
                    x=rocket.x,
                    y=rocket.y,
                    vx=math.cos(angle) * speed,
                    vy=math.sin(angle) * speed * 0.56,
                    life=0.45 + self._rand_float() * 0.35,
                    brightness=0.95,
                    theme=rocket.theme,
                    kind="spark",
                )
            )

        self._particles = self._particles[-280:]

    def _update_particles(self, *, rows: int, cols: int, crackle: float) -> None:
        drag = 0.985
        gravity = 0.045
        next_particles: list[_Particle] = []
        for particle in self._particles:
            particle.vx *= drag
            particle.vy = (particle.vy * drag) + gravity
            particle.x += particle.vx
            particle.y += particle.vy
            particle.life -= 0.022 if particle.kind == "main" else 0.038
            particle.brightness = max(
                0.0, particle.brightness - (0.018 + (0.03 * crackle))
            )
            if (
                particle.life <= 0
                or particle.brightness <= 0
                or particle.x < -1
                or particle.x > cols
                or particle.y < -1
                or particle.y > rows + 1
            ):
                continue
            next_particles.append(particle)
        self._particles = next_particles[-320:]

    def _rand_float(self) -> float:
        self._rng_state = (1103515245 * self._rng_state + 12345) & 0x7FFFFFFF
        return self._rng_state / 0x7FFFFFFF

    def _rand_int(self, n: int) -> int:
        if n <= 1:
            return 0
        return int(self._rand_float() * n) % n

    def _should_auto_launch(
        self,
        *,
        frame_index: int,
        energy: float,
        bass: float,
        highs: float,
        beat_strength: float,
    ) -> bool:
        energetic = energy >= 0.60 and (bass >= 0.54 or highs >= 0.56)
        if not energetic:
            return False
        cooldown = max(
            3, 8 - int(round(energy * 4.0)) - int(round(beat_strength * 2.0))
        )
        return (frame_index - self._last_launch_frame) >= cooldown


def _vu_level(frame: VisualizerFrameInput) -> float:
    levels = [
        value
        for value in (frame.level_left, frame.level_right)
        if value is not None and value >= 0
    ]
    if levels:
        return max(0.0, min(1.0, sum(levels) / len(levels)))
    return max(0.0, min(1.0, frame.volume / 100.0))


def _band_triplet(bands: bytes | None) -> tuple[float, float, float]:
    if not bands:
        return (0.0, 0.0, 0.0)
    size = len(bands)
    third = max(1, size // 3)
    lows = bands[:third]
    mids = bands[third : third * 2] or lows
    highs = bands[third * 2 :] or mids
    return (
        sum(lows) / (len(lows) * 255.0),
        sum(mids) / (len(mids) * 255.0),
        sum(highs) / (len(highs) * 255.0),
    )


def _waveform_roughness(frame: VisualizerFrameInput, fallback_high: float) -> float:
    spans: list[float] = []
    if frame.waveform_min_left is not None and frame.waveform_max_left is not None:
        spans.append(max(0.0, frame.waveform_max_left - frame.waveform_min_left))
    if frame.waveform_min_right is not None and frame.waveform_max_right is not None:
        spans.append(max(0.0, frame.waveform_max_right - frame.waveform_min_right))
    if not spans:
        return max(0.0, min(1.0, fallback_high))
    rough = sum(spans) / len(spans)
    return max(0.0, min(1.0, rough))


def _track_key(frame: VisualizerFrameInput) -> str:
    return "|".join(
        (
            frame.track_path or "",
            frame.title or "",
            frame.artist or "",
            frame.album or "",
            str(frame.duration_s or 0.0),
        )
    )


def _stable_seed(value: str) -> int:
    digest = sha256(value.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) or 1


def _theme_for_bands(bass: float, mids: float, highs: float) -> str:
    if bass >= mids and bass >= highs:
        return "hot"
    if highs >= mids and highs >= bass:
        return "spark"
    return "cool"


def _burst_type_for_bands(*, bass: float, high: float, rng: float) -> str:
    if bass > 0.62:
        return "willow" if rng > 0.45 else "palm"
    if high > 0.58:
        return "ring" if rng > 0.35 else "chrysanthemum"
    return "chrysanthemum"


def _spike_ratio(*, rocket_theme: str, bass: float, mids: float, highs: float) -> float:
    values = (bass, mids, highs)
    mean = max(0.0001, sum(values) / len(values))
    peak = max(values)
    theme_bias = 0.2 if rocket_theme == "spark" else 0.0
    return (peak / mean) + theme_bias


def _launch_energy(*, vu: float, bass: float, mids: float, highs: float) -> float:
    return max(
        0.0, min(1.0, (vu * 0.42) + (bass * 0.32) + (mids * 0.12) + (highs * 0.14))
    )


def _particle_glyph(brightness: float) -> str:
    if brightness >= 0.82:
        return "@"
    if brightness >= 0.62:
        return "#"
    if brightness >= 0.42:
        return "*"
    if brightness >= 0.24:
        return "+"
    return "."


def _status_line(
    *,
    beat_onset: bool,
    did_launch: bool,
    theme: str,
    bass: float,
    mids: float,
    highs: float,
    vu: float,
) -> str:
    mode = "LAUNCH" if beat_onset else ("SURGE" if did_launch else "IDLE")
    return (
        f"{mode} | "
        f"THEME {theme.upper()} | "
        f"VU {int(round(vu * 100)):3d}% | "
        f"L {int(round(bass * 100)):3d}% "
        f"M {int(round(mids * 100)):3d}% "
        f"H {int(round(highs * 100)):3d}%"
    )


def _render_rows(canvas: list[list[str]], *, ansi_enabled: bool) -> list[str]:
    if not ansi_enabled:
        return ["".join(row) for row in canvas]
    return ["".join(_colorize(cell) for cell in row) for row in canvas]


def _colorize(cell: str) -> str:
    if cell == " ":
        return cell
    if cell in {"|", "."}:
        return f"\x1b[38;2;170;190;220m{cell}\x1b[0m"
    if cell in {"+", "*"}:
        return f"\x1b[38;2;120;214;255m{cell}\x1b[0m"
    if cell in {"#", "X"}:
        return f"\x1b[38;2;255;140;220m{cell}\x1b[0m"
    if cell in {"@", "^"}:
        return f"\x1b[38;2;255;225;140m{cell}\x1b[0m"
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
