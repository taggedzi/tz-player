"""Tests for plasma-stream visualizer plugin."""

from __future__ import annotations

from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.plasma_stream import PlasmaStreamVisualizer
from tz_player.visualizers.registry import VisualizerRegistry


def _frame(*, beat_onset: bool = False) -> VisualizerFrameInput:
    return VisualizerFrameInput(
        frame_index=35,
        monotonic_s=0.0,
        width=96,
        height=24,
        status="playing",
        position_s=11.0,
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
        spectrum_bands=bytes([40, 72, 118, 158] * 12),
        beat_is_onset=beat_onset,
    )


def test_plasma_stream_plugin_registered() -> None:
    registry = VisualizerRegistry.built_in()
    assert registry.has_plugin("viz.particle.plasma_stream")


def test_plasma_stream_render_header_and_status() -> None:
    plugin = PlasmaStreamVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    output = plugin.render(_frame())
    assert "PLASMA STREAM FIELD" in output
    assert "FIELD FLOW" in output
    assert "MID" in output


def test_plasma_stream_render_field_invert_ansi() -> None:
    plugin = PlasmaStreamVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=True, unicode_enabled=True))
    output = plugin.render(_frame(beat_onset=True))
    assert "FIELD INVERT" in output
    assert "\x1b[" in output
