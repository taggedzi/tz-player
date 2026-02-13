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
    _tail_color: str
    _ansi_enabled: bool = True

    def on_activate(self, context: VisualizerContext) -> None:
        self._ansi_enabled = context.ansi_enabled

    def on_deactivate(self) -> None:
        return None

    def render(self, frame: VisualizerFrameInput) -> str:
        width = max(1, frame.width)
        height = max(1, frame.height)
        lines: list[str] = []
        for y in range(height):
            chars: list[str] = []
            for x in range(width):
                speed = 1 + ((x * 11) % 4)
                period = height + 14 + (x % 7)
                head = (frame.frame_index * speed + x * 17) % period - 7
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
                    chars.append(f"\x1b[{self._tail_color}m{glyph}\x1b[0m")
            lines.append("".join(chars))
        return "\n".join(lines)


@dataclass
class MatrixGreenVisualizer(_MatrixRainBase):
    plugin_id: str = "matrix.green"
    display_name: str = "Matrix Rain (Green)"
    _head_color: str = "92"
    _tail_color: str = "32"


@dataclass
class MatrixBlueVisualizer(_MatrixRainBase):
    plugin_id: str = "matrix.blue"
    display_name: str = "Matrix Rain (Blue)"
    _head_color: str = "96"
    _tail_color: str = "34"


@dataclass
class MatrixRedVisualizer(_MatrixRainBase):
    plugin_id: str = "matrix.red"
    display_name: str = "Matrix Rain (Red)"
    _head_color: str = "91"
    _tail_color: str = "31"
