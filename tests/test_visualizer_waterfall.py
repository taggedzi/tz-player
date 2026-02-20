"""Tests for spectrogram waterfall visualizer."""

from __future__ import annotations

import re

from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.registry import VisualizerRegistry
from tz_player.visualizers.waterfall import SpectrogramWaterfallVisualizer

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
        volume=80.0,
        speed=1.0,
        repeat_mode="OFF",
        shuffle=False,
        track_id=1,
        track_path="/tmp/song.mp3",
        title="Signal Bloom",
        artist="Grid Pilot",
        album="Cascade",
        spectrum_bands=spectrum_bands,
        spectrum_source=spectrum_source,
        spectrum_status=spectrum_status,
        beat_is_onset=beat_is_onset,
    )


def test_waterfall_plugin_is_registered_built_in() -> None:
    registry = VisualizerRegistry.built_in()
    assert registry.has_plugin("viz.spectrogram.waterfall")


def test_waterfall_plugin_declares_spectrum_requirement() -> None:
    plugin = SpectrogramWaterfallVisualizer()
    assert plugin.requires_spectrum is True


def test_waterfall_render_shows_fft_status_and_grid() -> None:
    plugin = SpectrogramWaterfallVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=False))
    output = plugin.render(
        _frame(
            width=36,
            height=8,
            frame_index=3,
            spectrum_bands=bytes([8, 20, 64, 96, 160, 220, 255, 180] * 6),
            spectrum_source="cache",
            spectrum_status="ready",
            beat_is_onset=False,
        )
    )
    assert "SPECTRO WATERFALL" in output
    assert "FFT READY [CACHE]" in output
    assert any(token in output for token in ("-", "=", "*", "#", "@"))


def test_waterfall_beat_onset_changes_newest_row() -> None:
    plugin = SpectrogramWaterfallVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=False))
    bands = bytes([30, 60, 90, 120, 150, 180, 210, 240] * 5)
    no_beat = plugin.render(
        _frame(
            width=30,
            height=7,
            frame_index=1,
            spectrum_bands=bands,
            spectrum_source="cache",
            spectrum_status="ready",
            beat_is_onset=False,
        )
    )
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=False))
    beat = plugin.render(
        _frame(
            width=30,
            height=7,
            frame_index=1,
            spectrum_bands=bands,
            spectrum_source="cache",
            spectrum_status="ready",
            beat_is_onset=True,
        )
    )
    assert no_beat != beat
    assert "BEAT ONSET" in beat


def test_waterfall_render_is_deterministic_after_reactivation() -> None:
    plugin = SpectrogramWaterfallVisualizer()
    context = VisualizerContext(ansi_enabled=False, unicode_enabled=True)
    frame = _frame(
        width=28,
        height=6,
        frame_index=4,
        spectrum_bands=bytes([10, 40, 80, 120, 160, 200, 240, 255] * 4),
        spectrum_source="cache",
        spectrum_status="ready",
        beat_is_onset=False,
    )
    plugin.on_activate(context)
    first = plugin.render(frame)
    plugin.on_deactivate()
    plugin.on_activate(context)
    assert first == plugin.render(frame)


def test_waterfall_ansi_output_stays_within_requested_width() -> None:
    plugin = SpectrogramWaterfallVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=True, unicode_enabled=True))
    output = plugin.render(
        _frame(
            width=24,
            height=6,
            frame_index=2,
            spectrum_bands=bytes([0, 32, 64, 96, 128, 160, 192, 224] * 3),
            spectrum_source="cache",
            spectrum_status="ready",
            beat_is_onset=True,
        )
    )
    assert "\x1b[38;2;" in output
    for line in output.splitlines():
        assert len(_SGR_PATTERN.sub("", line)) <= 24
