"""Tests for magnetic-grid visualizer plugin."""

from __future__ import annotations

from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.magnetic_grid import MagneticGridVisualizer
from tz_player.visualizers.registry import VisualizerRegistry


def _frame(*, beat_onset: bool = False) -> VisualizerFrameInput:
    return VisualizerFrameInput(
        frame_index=27,
        monotonic_s=0.0,
        width=90,
        height=24,
        status="playing",
        position_s=7.0,
        duration_s=180.0,
        volume=70.0,
        speed=1.0,
        repeat_mode="OFF",
        shuffle=False,
        track_id=1,
        track_path="/tmp/track.mp3",
        title="Track",
        artist="Artist",
        album="Album",
        spectrum_bands=bytes([32, 64, 110, 150] * 12),
        beat_is_onset=beat_onset,
    )


def test_magnetic_grid_plugin_registered() -> None:
    registry = VisualizerRegistry.built_in()
    assert registry.has_plugin("viz.particle.magnetic_grid")


def test_magnetic_grid_render_header_and_status() -> None:
    plugin = MagneticGridVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    output = plugin.render(_frame())
    assert "MAGNETIC GRID DISTORTION" in output
    assert "GRID FLOW" in output
    assert "MID" in output


def test_magnetic_grid_render_beat_pulse_ansi() -> None:
    plugin = MagneticGridVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=True, unicode_enabled=True))
    output = plugin.render(_frame(beat_onset=True))
    assert "GRID PULSE" in output
    assert "\x1b[" in output
