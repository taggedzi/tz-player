"""Tests for beat-triggered fireworks visualizer plugin."""

from __future__ import annotations

from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.fireworks import FireworksVisualizer
from tz_player.visualizers.registry import VisualizerRegistry


def _frame(
    *,
    frame_index: int = 10,
    beat_onset: bool = False,
    level_left: float = 0.66,
    level_right: float = 0.61,
    spectrum_bands: bytes | None = None,
) -> VisualizerFrameInput:
    return VisualizerFrameInput(
        frame_index=frame_index,
        monotonic_s=0.0,
        width=96,
        height=24,
        status="playing",
        position_s=12.0,
        duration_s=180.0,
        volume=74.0,
        speed=1.0,
        repeat_mode="OFF",
        shuffle=False,
        track_id=1,
        track_path="/tmp/track.mp3",
        title="Track",
        artist="Artist",
        album="Album",
        level_left=level_left,
        level_right=level_right,
        spectrum_bands=spectrum_bands or bytes([45, 68, 112, 165] * 12),
        beat_is_onset=beat_onset,
        waveform_min_left=-0.65,
        waveform_max_left=0.74,
        waveform_min_right=-0.62,
        waveform_max_right=0.70,
    )


def test_fireworks_plugin_registered() -> None:
    registry = VisualizerRegistry.built_in()
    assert registry.has_plugin("viz.particle.fireworks")


def test_fireworks_render_header_and_status() -> None:
    plugin = FireworksVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    output = plugin.render(_frame())
    assert "BEAT FIREWORKS" in output
    assert "THEME" in output
    assert "VU" in output


def test_fireworks_render_launch_and_ansi() -> None:
    plugin = FireworksVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=True, unicode_enabled=True))
    output_a = plugin.render(_frame(frame_index=50, beat_onset=True))
    output_b = plugin.render(_frame(frame_index=51, beat_onset=False))
    assert "LAUNCH" in output_a
    assert "\x1b[" in output_b


def test_fireworks_auto_launch_on_high_energy_frames_without_onset() -> None:
    plugin = FireworksVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    output = plugin.render(
        _frame(
            frame_index=120,
            beat_onset=False,
            level_left=0.93,
            level_right=0.91,
            spectrum_bands=bytes([228, 206, 214, 224] * 12),
        )
    )
    assert "SURGE" in output
