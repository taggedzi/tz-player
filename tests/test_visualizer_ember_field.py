"""Tests for ember-field visualizer plugin."""

from __future__ import annotations

from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.ember_field import EmberFieldVisualizer
from tz_player.visualizers.registry import VisualizerRegistry


def _frame(*, beat_onset: bool = False) -> VisualizerFrameInput:
    return VisualizerFrameInput(
        frame_index=23,
        monotonic_s=0.0,
        width=86,
        height=24,
        status="playing",
        position_s=6.0,
        duration_s=180.0,
        volume=72.0,
        speed=1.0,
        repeat_mode="OFF",
        shuffle=False,
        track_id=1,
        track_path="/tmp/track.mp3",
        title="Track",
        artist="Artist",
        album="Album",
        level_left=0.59,
        level_right=0.57,
        spectrum_bands=bytes([30, 62, 105, 148] * 12),
        beat_is_onset=beat_onset,
    )


def test_ember_field_plugin_registered() -> None:
    registry = VisualizerRegistry.built_in()
    assert registry.has_plugin("viz.particle.ember_field")


def test_ember_field_render_header_and_status() -> None:
    plugin = EmberFieldVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    output = plugin.render(_frame())
    assert "EMBER FIELD" in output
    assert "GLOW" in output
    assert "BASS" in output


def test_ember_field_render_beat_flare_ansi() -> None:
    plugin = EmberFieldVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=True, unicode_enabled=True))
    output = plugin.render(_frame(beat_onset=True))
    assert "FLARE" in output
    assert "\x1b[" in output
