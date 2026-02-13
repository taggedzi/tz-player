"""Tests for matrix rain visualizer variants."""

from __future__ import annotations

from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.matrix import (
    MatrixBlueVisualizer,
    MatrixGreenVisualizer,
    MatrixRedVisualizer,
)
from tz_player.visualizers.registry import VisualizerRegistry


def _frame(*, width: int, height: int, frame_index: int = 0) -> VisualizerFrameInput:
    return VisualizerFrameInput(
        frame_index=frame_index,
        monotonic_s=0.0,
        width=width,
        height=height,
        status="playing",
        position_s=1.0,
        duration_s=10.0,
        volume=100.0,
        speed=1.0,
        repeat_mode="OFF",
        shuffle=False,
        track_id=None,
        track_path=None,
        title=None,
        artist=None,
        album=None,
    )


def test_matrix_variants_are_registered_built_in() -> None:
    registry = VisualizerRegistry.built_in()
    assert registry.has_plugin("matrix.green")
    assert registry.has_plugin("matrix.blue")
    assert registry.has_plugin("matrix.red")


def test_matrix_render_is_deterministic_for_same_frame() -> None:
    plugin = MatrixGreenVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    frame = _frame(width=12, height=4, frame_index=25)
    output1 = plugin.render(frame)
    output2 = plugin.render(frame)
    assert output1 == output2


def test_matrix_render_respects_resize_bounds() -> None:
    plugin = MatrixBlueVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    small = plugin.render(_frame(width=8, height=3, frame_index=8))
    large = plugin.render(_frame(width=16, height=6, frame_index=8))

    small_lines = small.splitlines()
    large_lines = large.splitlines()
    assert len(small_lines) == 3
    assert len(large_lines) == 6
    assert all(len(line) == 8 for line in small_lines)
    assert all(len(line) == 16 for line in large_lines)


def test_matrix_variants_emit_ansi_color_when_enabled() -> None:
    plugin = MatrixRedVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=True, unicode_enabled=True))
    output = plugin.render(_frame(width=10, height=3, frame_index=4))
    assert "\x1b[" in output
    assert "38;2;" in output
