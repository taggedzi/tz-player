"""Tests for radial spectrum visualizer."""

from __future__ import annotations

import re

from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.radial import RadialSpectrumVisualizer
from tz_player.visualizers.registry import VisualizerRegistry

_SGR_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


def _frame(
    *,
    width: int,
    height: int,
    frame_index: int = 0,
    beat_is_onset: bool | None = None,
    spectrum_bands: bytes | None = None,
    spectrum_source: str | None = None,
    spectrum_status: str | None = None,
) -> VisualizerFrameInput:
    return VisualizerFrameInput(
        frame_index=frame_index,
        monotonic_s=0.0,
        width=width,
        height=height,
        status="playing",
        position_s=3.0,
        duration_s=120.0,
        volume=80.0,
        speed=1.0,
        repeat_mode="OFF",
        shuffle=False,
        track_id=1,
        track_path="/tmp/audio/radial.mp3",
        title="Radial Signal",
        artist="Signal Bloom",
        album="Arc",
        beat_is_onset=beat_is_onset,
        spectrum_bands=spectrum_bands,
        spectrum_source=spectrum_source,
        spectrum_status=spectrum_status,
    )


def test_radial_plugin_is_registered_built_in() -> None:
    registry = VisualizerRegistry.built_in()
    assert registry.has_plugin("viz.spectrum.radial")


def test_radial_plugin_declares_spectrum_and_beat_requirements() -> None:
    plugin = RadialSpectrumVisualizer()
    assert plugin.requires_spectrum is True
    assert plugin.requires_beat is True


def test_radial_render_shows_status_and_spokes() -> None:
    plugin = RadialSpectrumVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    output = plugin.render(
        _frame(
            width=40,
            height=10,
            frame_index=6,
            beat_is_onset=False,
            spectrum_bands=bytes([10, 30, 50, 80, 120, 160, 200, 240] * 6),
            spectrum_source="cache",
            spectrum_status="ready",
        )
    )
    assert "RADIAL SPECTRUM" in output
    assert "FFT READY [CACHE]" in output
    assert any(char in output for char in (".", "*", "@"))


def test_radial_beat_onset_changes_output() -> None:
    plugin = RadialSpectrumVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    idle = plugin.render(
        _frame(
            width=34,
            height=9,
            frame_index=10,
            beat_is_onset=False,
            spectrum_bands=bytes([20, 40, 60, 90, 130, 170, 210, 250] * 4),
            spectrum_source="cache",
            spectrum_status="ready",
        )
    )
    onset = plugin.render(
        _frame(
            width=34,
            height=9,
            frame_index=10,
            beat_is_onset=True,
            spectrum_bands=bytes([20, 40, 60, 90, 130, 170, 210, 250] * 4),
            spectrum_source="cache",
            spectrum_status="ready",
        )
    )
    assert idle != onset
    assert "BEAT ONSET" in onset


def test_radial_render_is_deterministic_after_reactivation() -> None:
    plugin = RadialSpectrumVisualizer()
    context = VisualizerContext(ansi_enabled=False, unicode_enabled=True)
    frame = _frame(
        width=30,
        height=8,
        frame_index=12,
        beat_is_onset=True,
        spectrum_bands=bytes([5, 25, 45, 65, 95, 125, 165, 205, 245] * 3),
        spectrum_source="cache",
        spectrum_status="ready",
    )
    plugin.on_activate(context)
    first = plugin.render(frame)
    plugin.on_deactivate()
    plugin.on_activate(context)
    assert first == plugin.render(frame)


def test_radial_ansi_output_stays_within_requested_width() -> None:
    plugin = RadialSpectrumVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=True, unicode_enabled=True))
    output = plugin.render(
        _frame(
            width=26,
            height=8,
            frame_index=9,
            beat_is_onset=True,
            spectrum_bands=bytes([8, 18, 35, 70, 110, 150, 190, 230, 255] * 3),
            spectrum_source="cache",
            spectrum_status="ready",
        )
    )
    assert "\x1b[38;2;" in output
    for line in output.splitlines():
        assert len(_SGR_PATTERN.sub("", line)) <= 26
