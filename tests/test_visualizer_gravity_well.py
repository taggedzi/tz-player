"""Tests for gravity-well particle visualizer plugin."""

from __future__ import annotations

from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.gravity_well import GravityWellVisualizer
from tz_player.visualizers.registry import VisualizerRegistry


def _frame(
    *, beat_onset: bool = False, spectrum: bytes | None = None
) -> VisualizerFrameInput:
    return VisualizerFrameInput(
        frame_index=12,
        monotonic_s=0.0,
        width=90,
        height=24,
        status="playing",
        position_s=2.0,
        duration_s=180.0,
        volume=80.0,
        speed=1.0,
        repeat_mode="OFF",
        shuffle=False,
        track_id=1,
        track_path="/tmp/track.mp3",
        title="Track",
        artist="Artist",
        album="Album",
        level_left=0.62,
        level_right=0.55,
        spectrum_bands=spectrum or bytes([20, 40, 80, 120] * 12),
        beat_is_onset=beat_onset,
    )


def test_gravity_well_plugin_registered() -> None:
    registry = VisualizerRegistry.built_in()
    assert registry.has_plugin("viz.particle.gravity_well")


def test_gravity_well_render_has_header_and_status() -> None:
    plugin = GravityWellVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    output = plugin.render(_frame())
    assert "GRAVITY WELL REACTOR" in output
    assert "RMS" in output
    assert "BASS" in output


def test_gravity_well_render_with_beat_burst_and_ansi() -> None:
    plugin = GravityWellVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=True, unicode_enabled=True))
    output = plugin.render(_frame(beat_onset=True))
    assert "BURST" in output
    assert "\x1b[" in output
