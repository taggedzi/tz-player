"""Tests for orbital-system visualizer plugin."""

from __future__ import annotations

from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.orbital_system import OrbitalSystemVisualizer
from tz_player.visualizers.registry import VisualizerRegistry


def _frame(*, beat_onset: bool = False) -> VisualizerFrameInput:
    return VisualizerFrameInput(
        frame_index=18,
        monotonic_s=0.0,
        width=92,
        height=24,
        status="playing",
        position_s=5.0,
        duration_s=200.0,
        volume=75.0,
        speed=1.0,
        repeat_mode="OFF",
        shuffle=False,
        track_id=1,
        track_path="/tmp/track.mp3",
        title="Track",
        artist="Artist",
        album="Album",
        level_left=0.58,
        level_right=0.61,
        spectrum_bands=bytes([35, 60, 100, 145] * 12),
        beat_is_onset=beat_onset,
    )


def test_orbital_system_plugin_registered() -> None:
    registry = VisualizerRegistry.built_in()
    assert registry.has_plugin("viz.particle.orbital_system")


def test_orbital_system_render_header_and_status() -> None:
    plugin = OrbitalSystemVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    output = plugin.render(_frame())
    assert "ORBITAL AUDIO SYSTEM" in output
    assert "BASS" in output
    assert "MID" in output
    assert "HIGH" in output


def test_orbital_system_render_beat_pulse_ansi() -> None:
    plugin = OrbitalSystemVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=True, unicode_enabled=True))
    output = plugin.render(_frame(beat_onset=True))
    assert "PULSE" in output
    assert "\x1b[" in output
