"""Matrix rain visualizer variants."""

from __future__ import annotations

from dataclasses import dataclass

from .base import VisualizerContext, VisualizerFrameInput

_GLYPHS = "0123456789ABCDEF$#@%&*+=-"


@dataclass
class _MatrixRainBase:
    plugin_id: str
    display_name: str
    _head_color: str
    _tail_palette: tuple[int, ...]
    _ansi_enabled: bool = True

    def on_activate(self, context: VisualizerContext) -> None:
        self._ansi_enabled = context.ansi_enabled

    def on_deactivate(self) -> None:
        return None

    def render(self, frame: VisualizerFrameInput) -> str:
        width = max(1, frame.width)
        height = max(1, frame.height)
        # Slow global fall cadence by ~20% for a calmer matrix effect.
        fall_tick = max(0, (frame.frame_index * 4) // 5)
        lines: list[str] = []
        for y in range(height):
            chars: list[str] = []
            for x in range(width):
                speed = 1 + ((x * 11) % 4)
                period = height + 14 + (x % 7)
                head = (fall_tick * speed + x * 17) % period - 7
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
                    chars.append(f"\x1b[1;{self._head_color}m{glyph}\x1b[0m")
                else:
                    color = _trail_color(self._tail_palette, distance, trail)
                    chars.append(f"\x1b[38;5;{color}m{glyph}\x1b[0m")
            lines.append("".join(chars))
        return "\n".join(lines)


@dataclass
class MatrixGreenVisualizer(_MatrixRainBase):
    plugin_id: str = "matrix.green"
    display_name: str = "Matrix Rain (Green)"
    _head_color: str = "92"
    _tail_palette: tuple[int, ...] = (120, 82, 46, 40, 34, 28, 22)


@dataclass
class MatrixBlueVisualizer(_MatrixRainBase):
    plugin_id: str = "matrix.blue"
    display_name: str = "Matrix Rain (Blue)"
    _head_color: str = "96"
    _tail_palette: tuple[int, ...] = (153, 117, 81, 45, 39, 33, 17)


@dataclass
class MatrixRedVisualizer(_MatrixRainBase):
    plugin_id: str = "matrix.red"
    display_name: str = "Matrix Rain (Red)"
    _head_color: str = "91"
    _tail_palette: tuple[int, ...] = (217, 203, 167, 131, 125, 89, 52)


def _trail_color(palette: tuple[int, ...], distance: int, trail: int) -> int:
    if not palette:
        return 22
    if trail <= 1:
        return palette[0]
    ratio = min(max(distance / (trail - 1), 0.0), 1.0)
    index = int(round(ratio * (len(palette) - 1)))
    return palette[index]
