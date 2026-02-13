"""Tests for fictional cyberpunk ops visualizer."""

from __future__ import annotations

from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.ops_cyberpunk import CyberpunkOpsVisualizer
from tz_player.visualizers.registry import VisualizerRegistry


def _frame(
    *,
    width: int,
    height: int,
    frame_index: int = 0,
    status: str = "playing",
) -> VisualizerFrameInput:
    return VisualizerFrameInput(
        frame_index=frame_index,
        monotonic_s=0.0,
        width=width,
        height=height,
        status=status,
        position_s=12.0,
        duration_s=200.0,
        volume=73.0,
        speed=1.0,
        repeat_mode="OFF",
        shuffle=False,
        track_id=1,
        track_path="/tmp/track.mp3",
        title="Neon Shadow",
        artist="Proxy Unit",
        album="Gridline",
    )


def test_ops_plugin_is_registered_built_in() -> None:
    registry = VisualizerRegistry.built_in()
    assert registry.has_plugin("ops.cyberpunk")


def test_ops_render_contains_fictional_stage_and_metadata() -> None:
    plugin = CyberpunkOpsVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    output = plugin.render(_frame(width=70, height=8, frame_index=21))
    assert "[SIMULATION]" in output
    assert "NON-OPERATIONAL" in output
    assert "TARGET: Neon Shadow :: Proxy Unit" in output
    assert "STAGE:" in output
    assert "ops@nightcity:~$" in output
    assert "[run]" in output


def test_ops_render_is_deterministic_for_same_frame() -> None:
    plugin = CyberpunkOpsVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    frame = _frame(width=60, height=8, frame_index=45)
    assert plugin.render(frame) == plugin.render(frame)


def test_ops_render_respects_resize_bounds() -> None:
    plugin = CyberpunkOpsVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    small = plugin.render(_frame(width=20, height=4, frame_index=10))
    small_lines = small.splitlines()
    assert len(small_lines) == 4
    assert all(len(line) <= 20 for line in small_lines)


def test_ops_render_fills_available_height() -> None:
    plugin = CyberpunkOpsVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    tall = plugin.render(_frame(width=60, height=16, frame_index=8))
    assert len(tall.splitlines()) == 16


def test_ops_render_includes_minigame_output_during_run_phase() -> None:
    plugin = CyberpunkOpsVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    output = plugin.render(_frame(width=90, height=16, frame_index=9))
    assert "[mini]" in output


def test_ops_commands_advance_one_at_a_time_with_result_history() -> None:
    plugin = CyberpunkOpsVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    first = plugin.render(_frame(width=90, height=18, frame_index=0))
    second = plugin.render(_frame(width=90, height=18, frame_index=24))
    assert "simscope survey --target track://current --passive" in first
    assert "simscope map-signal --window 8s --no-write" in second
    assert "simscope survey --target track://current --passive" in second
    assert "[ok]" in second
