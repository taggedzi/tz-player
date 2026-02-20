"""Tests for reactive particle-rain visualizer plugin."""

from __future__ import annotations

from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.rain_reactive import ReactiveRainVisualizer
from tz_player.visualizers.registry import VisualizerRegistry


def _frame(*, beat_onset: bool = False) -> VisualizerFrameInput:
    return VisualizerFrameInput(
        frame_index=15,
        monotonic_s=0.0,
        width=84,
        height=22,
        status="playing",
        position_s=4.0,
        duration_s=180.0,
        volume=75.0,
        speed=1.0,
        repeat_mode="OFF",
        shuffle=False,
        track_id=1,
        track_path="/tmp/track.mp3",
        title="Track",
        artist="Artist",
        album="Album",
        level_left=0.60,
        level_right=0.51,
        spectrum_bands=bytes([30, 50, 95, 140] * 12),
        beat_is_onset=beat_onset,
    )


def test_reactive_rain_plugin_registered() -> None:
    registry = VisualizerRegistry.built_in()
    assert registry.has_plugin("viz.particle.rain_reactive")


def test_reactive_rain_render_header_status() -> None:
    plugin = ReactiveRainVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    output = plugin.render(_frame())
    assert "REACTIVE PARTICLE RAIN" in output
    assert "FLOW" in output
    assert "RMS" in output


def test_reactive_rain_render_beat_surge_ansi() -> None:
    plugin = ReactiveRainVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=True, unicode_enabled=True))
    output = plugin.render(_frame(beat_onset=True))
    assert "SURGE" in output
    assert "\x1b[" in output
