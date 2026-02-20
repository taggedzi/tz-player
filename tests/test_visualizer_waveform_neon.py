"""Tests for colorful waveform-neon visualizer plugin."""

from __future__ import annotations

from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.registry import VisualizerRegistry
from tz_player.visualizers.waveform_neon import WaveformNeonVisualizer


def _frame(
    *,
    width: int = 56,
    height: int = 12,
    waveform_status: str | None = "ready",
) -> VisualizerFrameInput:
    return VisualizerFrameInput(
        frame_index=7,
        monotonic_s=0.0,
        width=width,
        height=height,
        status="playing",
        position_s=4.0,
        duration_s=100.0,
        volume=100.0,
        speed=1.0,
        repeat_mode="OFF",
        shuffle=False,
        track_id=1,
        track_path="/tmp/song.mp3",
        title="Song",
        artist="Artist",
        album="Album",
        waveform_min_left=-0.8 if waveform_status else None,
        waveform_max_left=0.6 if waveform_status else None,
        waveform_min_right=-0.5 if waveform_status else None,
        waveform_max_right=0.7 if waveform_status else None,
        waveform_source="cache" if waveform_status else None,
        waveform_status=waveform_status,
        level_left=0.5,
        level_right=0.4,
    )


def test_waveform_neon_plugin_is_registered_built_in() -> None:
    registry = VisualizerRegistry.built_in()
    assert registry.has_plugin("viz.waveform.neon")


def test_waveform_neon_render_includes_header_and_status() -> None:
    plugin = WaveformNeonVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    output = plugin.render(_frame())
    assert "WaveformNeon" in output
    assert "L span" in output
    assert "R span" in output


def test_waveform_neon_uses_fallback_source_when_proxy_missing() -> None:
    plugin = WaveformNeonVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=True, unicode_enabled=True))
    output = plugin.render(_frame(waveform_status=None))
    assert "fallback" in output
    assert "\x1b[" in output
