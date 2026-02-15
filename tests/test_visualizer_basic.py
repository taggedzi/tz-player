"""Tests for basic visualizer behavior."""

from __future__ import annotations

from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.basic import BasicVisualizer


def _frame(*, status: str) -> VisualizerFrameInput:
    return VisualizerFrameInput(
        frame_index=0,
        monotonic_s=0.0,
        width=20,
        height=3,
        status=status,
        position_s=1.0,
        duration_s=10.0,
        volume=1.0,
        speed=1.0,
        repeat_mode="OFF",
        shuffle=False,
        track_id=None,
        track_path=None,
        title=None,
        artist=None,
        album=None,
    )


def test_basic_visualizer_non_playback_status_text() -> None:
    plugin = BasicVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    assert plugin.render(_frame(status="idle")) == "Idle"
    assert plugin.render(_frame(status="stopped")) == "Idle"
    assert plugin.render(_frame(status="loading")) == "Loading"
    assert plugin.render(_frame(status="error")) == "Error"
