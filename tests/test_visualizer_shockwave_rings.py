"""Tests for shockwave-rings visualizer plugin."""

from __future__ import annotations

from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.registry import VisualizerRegistry
from tz_player.visualizers.shockwave_rings import ShockwaveRingsVisualizer


def _frame(*, beat_onset: bool = False) -> VisualizerFrameInput:
    return VisualizerFrameInput(
        frame_index=21,
        monotonic_s=0.0,
        width=88,
        height=24,
        status="playing",
        position_s=3.0,
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
        level_left=0.58,
        level_right=0.52,
        spectrum_bands=bytes([25, 45, 90, 130] * 12),
        beat_is_onset=beat_onset,
        beat_strength=0.75 if beat_onset else 0.0,
    )


def test_shockwave_rings_plugin_registered() -> None:
    registry = VisualizerRegistry.built_in()
    assert registry.has_plugin("viz.particle.shockwave_rings")


def test_shockwave_rings_render_header_and_status() -> None:
    plugin = ShockwaveRingsVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    output = plugin.render(_frame())
    assert "AUDIO SHOCKWAVE RINGS" in output
    assert "RING FLOW" in output
    assert "BASS" in output


def test_shockwave_rings_render_beat_burst_ansi() -> None:
    plugin = ShockwaveRingsVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=True, unicode_enabled=True))
    output = plugin.render(_frame(beat_onset=True))
    assert "RING BURST" in output
    assert "\x1b[" in output
