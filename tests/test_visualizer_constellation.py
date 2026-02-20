"""Tests for constellation visualizer plugin."""

from __future__ import annotations

from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.constellation import ConstellationVisualizer
from tz_player.visualizers.registry import VisualizerRegistry


def _frame(*, beat_onset: bool = False) -> VisualizerFrameInput:
    return VisualizerFrameInput(
        frame_index=31,
        monotonic_s=0.0,
        width=96,
        height=24,
        status="playing",
        position_s=9.0,
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
        spectrum_bands=bytes([36, 68, 114, 154] * 12),
        beat_is_onset=beat_onset,
    )


def test_constellation_plugin_registered() -> None:
    registry = VisualizerRegistry.built_in()
    assert registry.has_plugin("viz.particle.constellation")


def test_constellation_render_header_and_status() -> None:
    plugin = ConstellationVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    output = plugin.render(_frame())
    assert "CONSTELLATION MODE" in output
    assert "STAR LINK" in output
    assert "MID" in output


def test_constellation_render_cluster_burst_ansi() -> None:
    plugin = ConstellationVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=True, unicode_enabled=True))
    output = plugin.render(_frame(beat_onset=True))
    assert "CLUSTER BURST" in output
    assert "\x1b[" in output
