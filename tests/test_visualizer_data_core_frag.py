"""Tests for data-core fragmentation visualizer plugin."""

from __future__ import annotations

from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.data_core_frag import DataCoreFragVisualizer
from tz_player.visualizers.registry import VisualizerRegistry


def _frame(*, beat_onset: bool = False) -> VisualizerFrameInput:
    return VisualizerFrameInput(
        frame_index=33,
        monotonic_s=0.0,
        width=92,
        height=24,
        status="playing",
        position_s=10.0,
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
        spectrum_bands=bytes([38, 70, 116, 156] * 12),
        beat_is_onset=beat_onset,
    )


def test_data_core_frag_plugin_registered() -> None:
    registry = VisualizerRegistry.built_in()
    assert registry.has_plugin("viz.particle.data_core_frag")


def test_data_core_frag_render_header_and_status() -> None:
    plugin = DataCoreFragVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    output = plugin.render(_frame())
    assert "DATA CORE FRAGMENTATION" in output
    assert "DRIFT" in output
    assert "MID" in output


def test_data_core_frag_render_fracture_ansi() -> None:
    plugin = DataCoreFragVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=True, unicode_enabled=True))
    output = plugin.render(_frame(beat_onset=True))
    assert "FRACTURE" in output
    assert "\x1b[" in output
