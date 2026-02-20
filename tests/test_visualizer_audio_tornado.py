"""Tests for audio-tornado visualizer plugin."""

from __future__ import annotations

from tz_player.visualizers.audio_tornado import AudioTornadoVisualizer
from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.registry import VisualizerRegistry


def _frame(*, beat_onset: bool = False) -> VisualizerFrameInput:
    return VisualizerFrameInput(
        frame_index=29,
        monotonic_s=0.0,
        width=92,
        height=24,
        status="playing",
        position_s=8.0,
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
        level_left=0.62,
        level_right=0.58,
        spectrum_bands=bytes([34, 66, 112, 152] * 12),
        beat_is_onset=beat_onset,
    )


def test_audio_tornado_plugin_registered() -> None:
    registry = VisualizerRegistry.built_in()
    assert registry.has_plugin("viz.particle.audio_tornado")


def test_audio_tornado_render_header_and_status() -> None:
    plugin = AudioTornadoVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    output = plugin.render(_frame())
    assert "AUDIO TORNADO" in output
    assert "SPIRAL" in output
    assert "MID" in output


def test_audio_tornado_render_beat_tighten_ansi() -> None:
    plugin = AudioTornadoVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=True, unicode_enabled=True))
    output = plugin.render(_frame(beat_onset=True))
    assert "TIGHTEN" in output
    assert "\x1b[" in output
