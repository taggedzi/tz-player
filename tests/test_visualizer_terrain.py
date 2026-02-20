"""Tests for audio terrain visualizer."""

from __future__ import annotations

import re

from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.registry import VisualizerRegistry
from tz_player.visualizers.terrain import AudioTerrainVisualizer

_SGR_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


def _frame(
    *,
    width: int,
    height: int,
    frame_index: int = 0,
    spectrum_bands: bytes | None = None,
    spectrum_source: str | None = None,
    spectrum_status: str | None = None,
    beat_is_onset: bool | None = None,
) -> VisualizerFrameInput:
    return VisualizerFrameInput(
        frame_index=frame_index,
        monotonic_s=0.0,
        width=width,
        height=height,
        status="playing",
        position_s=2.0,
        duration_s=120.0,
        volume=70.0,
        speed=1.0,
        repeat_mode="OFF",
        shuffle=False,
        track_id=1,
        track_path="/tmp/audio/song.mp3",
        title="Neon Dune",
        artist="Signal Bloom",
        album="Horizon",
        spectrum_bands=spectrum_bands,
        spectrum_source=spectrum_source,
        spectrum_status=spectrum_status,
        beat_is_onset=beat_is_onset,
    )


def test_terrain_plugin_is_registered_built_in() -> None:
    registry = VisualizerRegistry.built_in()
    assert registry.has_plugin("viz.spectrum.terrain")


def test_terrain_plugin_declares_spectrum_requirement() -> None:
    plugin = AudioTerrainVisualizer()
    assert plugin.requires_spectrum is True


def test_terrain_render_shows_fft_status_and_terrain() -> None:
    plugin = AudioTerrainVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    output = plugin.render(
        _frame(
            width=36,
            height=9,
            frame_index=4,
            spectrum_bands=bytes([10, 30, 50, 70, 90, 120, 170, 220, 255] * 5),
            spectrum_source="cache",
            spectrum_status="ready",
            beat_is_onset=False,
        )
    )
    assert "AUDIO TERRAIN" in output
    assert "FFT READY [CACHE]" in output
    assert any(token in output for token in ("^", "#", ":"))


def test_terrain_beat_onset_changes_landscape() -> None:
    plugin = AudioTerrainVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    bands = bytes([20, 40, 60, 80, 100, 150, 200, 220, 240] * 4)
    without_beat = plugin.render(
        _frame(
            width=30,
            height=8,
            frame_index=2,
            spectrum_bands=bands,
            spectrum_source="cache",
            spectrum_status="ready",
            beat_is_onset=False,
        )
    )
    with_beat = plugin.render(
        _frame(
            width=30,
            height=8,
            frame_index=2,
            spectrum_bands=bands,
            spectrum_source="cache",
            spectrum_status="ready",
            beat_is_onset=True,
        )
    )
    assert without_beat != with_beat
    assert "BEAT ONSET" in with_beat


def test_terrain_render_is_deterministic_after_reactivation() -> None:
    plugin = AudioTerrainVisualizer()
    context = VisualizerContext(ansi_enabled=False, unicode_enabled=True)
    frame = _frame(
        width=28,
        height=7,
        frame_index=11,
        spectrum_bands=bytes([0, 25, 55, 85, 115, 145, 175, 205, 235, 255] * 3),
        spectrum_source="cache",
        spectrum_status="ready",
        beat_is_onset=True,
    )
    plugin.on_activate(context)
    first = plugin.render(frame)
    plugin.on_deactivate()
    plugin.on_activate(context)
    assert first == plugin.render(frame)


def test_terrain_ansi_output_stays_within_requested_width() -> None:
    plugin = AudioTerrainVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=True, unicode_enabled=True))
    output = plugin.render(
        _frame(
            width=24,
            height=7,
            spectrum_bands=bytes([5, 35, 65, 95, 125, 155, 185, 215, 245] * 3),
            spectrum_source="cache",
            spectrum_status="ready",
            beat_is_onset=True,
        )
    )
    assert "\x1b[38;2;" in output
    for line in output.splitlines():
        assert len(_SGR_PATTERN.sub("", line)) <= 24
