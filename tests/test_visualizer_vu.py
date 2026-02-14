"""Tests for reactive VU visualizer."""

from __future__ import annotations

from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.registry import VisualizerRegistry
from tz_player.visualizers.vu import VuReactiveVisualizer


def _frame(
    *,
    width: int,
    height: int,
    frame_index: int = 0,
    status: str = "playing",
    level_left: float | None = None,
    level_right: float | None = None,
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
        level_left=level_left,
        level_right=level_right,
    )


def test_vu_plugin_is_registered_built_in() -> None:
    registry = VisualizerRegistry.built_in()
    assert registry.has_plugin("vu.reactive")


def test_vu_render_uses_live_levels_when_available() -> None:
    plugin = VuReactiveVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    output = plugin.render(
        _frame(width=72, height=8, frame_index=3, level_left=1.2, level_right=0.8)
    )
    assert "VU REACTIVE [LIVE]" in output
    assert "L [" in output
    assert "R [" in output


def test_vu_render_falls_back_when_levels_unavailable() -> None:
    plugin = VuReactiveVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    output = plugin.render(_frame(width=72, height=8, frame_index=3))
    assert "VU REACTIVE [SIM]" in output


def test_vu_render_is_deterministic_for_same_frame_after_reactivation() -> None:
    plugin = VuReactiveVisualizer()
    context = VisualizerContext(ansi_enabled=False, unicode_enabled=True)
    plugin.on_activate(context)
    frame = _frame(width=60, height=8, frame_index=10, level_left=0.4, level_right=0.7)
    first = plugin.render(frame)
    plugin.on_deactivate()
    plugin.on_activate(context)
    assert first == plugin.render(frame)


def test_vu_render_respects_resize_bounds() -> None:
    plugin = VuReactiveVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    output = plugin.render(_frame(width=20, height=4, frame_index=2))
    lines = output.splitlines()
    assert len(lines) == 4
    assert all(len(line) <= 20 for line in lines)
