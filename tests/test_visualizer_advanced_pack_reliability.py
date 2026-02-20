"""Reliability checks for advanced visualizer pack fallback behavior."""

from __future__ import annotations

from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.host import VisualizerHost
from tz_player.visualizers.registry import VisualizerRegistry

ADVANCED_VIZ_IDS = (
    "viz.spectrogram.waterfall",
    "viz.spectrum.terrain",
    "viz.reactor.particles",
    "viz.particle.gravity_well",
    "viz.spectrum.radial",
    "viz.typography.glitch",
    "viz.waveform.neon",
)


def _frame() -> VisualizerFrameInput:
    """Build frame payload with intentionally missing analysis data."""
    return VisualizerFrameInput(
        frame_index=1,
        monotonic_s=0.0,
        width=72,
        height=16,
        status="playing",
        position_s=1.0,
        duration_s=120.0,
        volume=65.0,
        speed=1.0,
        repeat_mode="OFF",
        shuffle=False,
        track_id=1,
        track_path="/tmp/track.mp3",
        title="Fallback Probe",
        artist="QA",
        album="Stability",
        spectrum_bands=None,
        spectrum_source=None,
        spectrum_status="missing",
        beat_strength=None,
        beat_is_onset=None,
        beat_bpm=None,
        beat_source=None,
        beat_status="missing",
    )


def test_advanced_visualizers_render_without_analysis_data_or_fallback() -> None:
    registry = VisualizerRegistry.built_in()
    host = VisualizerHost(registry)
    context = VisualizerContext(ansi_enabled=False, unicode_enabled=True)
    frame = _frame()
    for plugin_id in ADVANCED_VIZ_IDS:
        active = host.activate(plugin_id, context)
        assert active == plugin_id
        output = host.render_frame(frame, context)
        assert output
        assert host.active_id == plugin_id
