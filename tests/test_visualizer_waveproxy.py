"""Tests for waveform-proxy visualizer plugin."""

from __future__ import annotations

from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.registry import VisualizerRegistry
from tz_player.visualizers.waveproxy import WaveformProxyVisualizer


def _frame(
    *,
    width: int = 50,
    height: int = 4,
    waveform_status: str | None = "ready",
) -> VisualizerFrameInput:
    return VisualizerFrameInput(
        frame_index=0,
        monotonic_s=0.0,
        width=width,
        height=height,
        status="playing",
        position_s=1.0,
        duration_s=10.0,
        volume=100.0,
        speed=1.0,
        repeat_mode="OFF",
        shuffle=False,
        track_id=1,
        track_path="/tmp/song.mp3",
        title="Song",
        artist="Artist",
        album="Album",
        waveform_min_left=-0.7 if waveform_status else None,
        waveform_max_left=0.6 if waveform_status else None,
        waveform_min_right=-0.5 if waveform_status else None,
        waveform_max_right=0.4 if waveform_status else None,
        waveform_source="cache" if waveform_status else None,
        waveform_status=waveform_status,
        level_left=0.5,
        level_right=0.4,
    )


def test_waveform_proxy_plugin_is_registered_built_in() -> None:
    registry = VisualizerRegistry.built_in()
    assert registry.has_plugin("viz.waveform.proxy")


def test_waveform_proxy_render_includes_source_and_lanes() -> None:
    plugin = WaveformProxyVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    output = plugin.render(_frame())
    assert "WaveformProxy" in output
    assert "L: " in output
    assert "R: " in output


def test_waveform_proxy_falls_back_to_level_when_proxy_missing() -> None:
    plugin = WaveformProxyVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    output = plugin.render(_frame(waveform_status=None))
    assert "fallback" in output
    assert "L: " in output
