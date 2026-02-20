"""Tests for particle reactor visualizer."""

from __future__ import annotations

import re

from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.reactor import ParticleReactorVisualizer
from tz_player.visualizers.registry import VisualizerRegistry

_SGR_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


def _frame(
    *,
    width: int,
    height: int,
    frame_index: int = 0,
    beat_is_onset: bool | None = None,
    spectrum_bands: bytes | None = None,
    level_left: float | None = None,
    level_right: float | None = None,
) -> VisualizerFrameInput:
    return VisualizerFrameInput(
        frame_index=frame_index,
        monotonic_s=0.0,
        width=width,
        height=height,
        status="playing",
        position_s=3.0,
        duration_s=120.0,
        volume=72.0,
        speed=1.0,
        repeat_mode="OFF",
        shuffle=False,
        track_id=1,
        track_path="/tmp/audio/orbit.mp3",
        title="Orbit",
        artist="Signal Bloom",
        album="Reactor",
        beat_is_onset=beat_is_onset,
        spectrum_bands=spectrum_bands,
        level_left=level_left,
        level_right=level_right,
    )


def test_reactor_plugin_is_registered_built_in() -> None:
    registry = VisualizerRegistry.built_in()
    assert registry.has_plugin("viz.reactor.particles")


def test_reactor_plugin_declares_spectrum_and_beat_requirements() -> None:
    plugin = ParticleReactorVisualizer()
    assert plugin.requires_spectrum is True
    assert plugin.requires_beat is True


def test_reactor_render_shows_status_and_particles() -> None:
    plugin = ParticleReactorVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    output = plugin.render(
        _frame(
            width=40,
            height=10,
            frame_index=5,
            beat_is_onset=False,
            spectrum_bands=bytes([10, 20, 40, 80, 120, 160, 200, 240] * 6),
            level_left=0.60,
            level_right=0.55,
        )
    )
    assert "PARTICLE REACTOR" in output
    assert "BEAT IDLE" in output
    assert any(char in output for char in (".", "*", "+", "o", "O"))


def test_reactor_beat_onset_changes_output() -> None:
    plugin = ParticleReactorVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    idle = plugin.render(
        _frame(
            width=34,
            height=9,
            frame_index=8,
            beat_is_onset=False,
            spectrum_bands=bytes([20, 35, 50, 90, 130, 170, 210, 250] * 4),
        )
    )
    onset = plugin.render(
        _frame(
            width=34,
            height=9,
            frame_index=8,
            beat_is_onset=True,
            spectrum_bands=bytes([20, 35, 50, 90, 130, 170, 210, 250] * 4),
        )
    )
    assert idle != onset
    assert "BEAT ONSET" in onset


def test_reactor_render_is_deterministic_after_reactivation() -> None:
    plugin = ParticleReactorVisualizer()
    context = VisualizerContext(ansi_enabled=False, unicode_enabled=True)
    frame = _frame(
        width=30,
        height=8,
        frame_index=11,
        beat_is_onset=True,
        spectrum_bands=bytes([5, 25, 45, 65, 100, 140, 180, 220, 255] * 3),
        level_left=0.65,
        level_right=0.62,
    )
    plugin.on_activate(context)
    first = plugin.render(frame)
    plugin.on_deactivate()
    plugin.on_activate(context)
    assert first == plugin.render(frame)


def test_reactor_ansi_output_stays_within_requested_width() -> None:
    plugin = ParticleReactorVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=True, unicode_enabled=True))
    output = plugin.render(
        _frame(
            width=26,
            height=8,
            frame_index=9,
            beat_is_onset=True,
            spectrum_bands=bytes([8, 18, 35, 70, 110, 150, 190, 230, 255] * 3),
            level_left=0.7,
            level_right=0.6,
        )
    )
    assert "\x1b[38;2;" in output
    for line in output.splitlines():
        assert len(_SGR_PATTERN.sub("", line)) <= 26
