"""Tests for beat diagnostics visualizer plugin."""

from __future__ import annotations

from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.beat_scope import BeatScopeVisualizer
from tz_player.visualizers.registry import VisualizerRegistry


def _frame(
    *,
    frame_index: int = 10,
    beat_onset: bool = False,
    beat_strength: float | None = 0.0,
) -> VisualizerFrameInput:
    return VisualizerFrameInput(
        frame_index=frame_index,
        monotonic_s=0.0,
        width=88,
        height=16,
        status="playing",
        position_s=32.0,
        duration_s=300.0,
        volume=70.0,
        speed=1.0,
        repeat_mode="OFF",
        shuffle=False,
        track_id=1,
        track_path="/tmp/track.mp3",
        title="Track",
        artist="Artist",
        album="Album",
        beat_is_onset=beat_onset,
        beat_strength=beat_strength,
        beat_bpm=142.0,
        beat_source="cache",
        beat_status="ready",
    )


def test_beat_scope_plugin_registered() -> None:
    registry = VisualizerRegistry.built_in()
    assert registry.has_plugin("viz.debug.beat_scope")


def test_beat_scope_render_onset_and_history() -> None:
    plugin = BeatScopeVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    output_onset = plugin.render(
        _frame(frame_index=100, beat_onset=True, beat_strength=0.88)
    )
    output_idle = plugin.render(
        _frame(frame_index=101, beat_onset=False, beat_strength=0.22)
    )
    assert "BEAT SCOPE (DEBUG)" in output_onset
    assert "BEAT ONSET" in output_onset
    assert "ONSETS [" in output_idle
    assert "|" in output_idle


def test_beat_scope_render_ansi_colors() -> None:
    plugin = BeatScopeVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=True, unicode_enabled=True))
    output = plugin.render(_frame(frame_index=50, beat_onset=True, beat_strength=0.95))
    assert "\x1b[" in output
