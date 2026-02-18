"""Deterministic matrix-rain visualizer family (green/blue/red themes)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .base import VisualizerContext, VisualizerFrameInput

_GLYPHS = "0123456789ABCDEF$#@%&*+=-"


@dataclass
class _MatrixRainBase:
    """Shared matrix-rain renderer parametrized by theme colors."""

    plugin_id: str
    display_name: str
    _head_rgb: tuple[int, int, int]
    _trail_rgb: tuple[int, int, int]
    _ansi_enabled: bool = True

    def on_activate(self, context: VisualizerContext) -> None:
        self._ansi_enabled = context.ansi_enabled

    def on_deactivate(self) -> None:
        return None

    def render(self, frame: VisualizerFrameInput) -> str:
        """Render time-driven falling glyph columns for the current viewport."""
        width = max(1, frame.width)
        height = max(1, frame.height)
        monotonic_s = frame.monotonic_s if math.isfinite(frame.monotonic_s) else 0.0
        # Use continuous monotonic time to avoid quantized per-frame jumps/stutter.
        # Tuned to feel smooth while remaining slower than the earlier cadence.
        base_rows_per_second = 7.5
        lines: list[str] = []
        for y in range(height):
            chars: list[str] = []
            for x in range(width):
                speed_scale = 0.75 + ((x * 11) % 4) * 0.2
                period = height + 14 + (x % 7)
                head = (
                    monotonic_s * base_rows_per_second * speed_scale + x * 17
                ) % period - 7
                trail = 5 + (x % 6)
                distance = head - y
                if distance < 0 or distance >= trail:
                    chars.append(" ")
                    continue
                glyph = _GLYPHS[(x * 13 + y * 7 + frame.frame_index) % len(_GLYPHS)]
                if not self._ansi_enabled:
                    chars.append(glyph)
                    continue
                if distance == 0:
                    chars.append(f"\x1b[1;{_rgb_code(self._head_rgb)}m{glyph}\x1b[0m")
                else:
                    trail_rgb = _trail_rgb(self._trail_rgb, distance, trail)
                    chars.append(f"\x1b[{_rgb_code(trail_rgb)}m{glyph}\x1b[0m")
            lines.append("".join(chars))
        return "\n".join(lines)


@dataclass
class MatrixGreenVisualizer(_MatrixRainBase):
    plugin_id: str = "matrix.green"
    display_name: str = "Matrix Rain (Green)"
    _head_rgb: tuple[int, int, int] = (215, 255, 220)
    _trail_rgb: tuple[int, int, int] = (0, 255, 110)


@dataclass
class MatrixBlueVisualizer(_MatrixRainBase):
    plugin_id: str = "matrix.blue"
    display_name: str = "Matrix Rain (Blue)"
    _head_rgb: tuple[int, int, int] = (210, 240, 255)
    _trail_rgb: tuple[int, int, int] = (0, 180, 255)


@dataclass
class MatrixRedVisualizer(_MatrixRainBase):
    plugin_id: str = "matrix.red"
    display_name: str = "Matrix Rain (Red)"
    _head_rgb: tuple[int, int, int] = (255, 220, 220)
    _trail_rgb: tuple[int, int, int] = (255, 75, 75)


def _trail_rgb(
    base_rgb: tuple[int, int, int], distance: float, trail: int
) -> tuple[int, int, int]:
    """Fade trail color intensity as distance from glyph head increases."""
    if trail <= 1:
        return base_rgb
    ratio = min(max(distance / (trail - 1), 0.0), 1.0)
    # Fade from ~80% of base brightness down to ~8% for near-invisible tail.
    brightness = 0.8 - ratio * 0.72
    r, g, b = base_rgb
    return (
        max(0, min(255, int(round(r * brightness)))),
        max(0, min(255, int(round(g * brightness)))),
        max(0, min(255, int(round(b * brightness)))),
    )


def _rgb_code(rgb: tuple[int, int, int]) -> str:
    """Build ANSI truecolor foreground code fragment for an RGB tuple."""
    r, g, b = rgb
    return f"38;2;{r};{g};{b}"
