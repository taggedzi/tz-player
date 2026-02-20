"""Tests for typography glitch visualizer."""

from __future__ import annotations

import re

from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.registry import VisualizerRegistry
from tz_player.visualizers.typography import TypographyGlitchVisualizer

_SGR_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


def _frame(
    *,
    width: int,
    height: int,
    frame_index: int = 0,
    title: str | None = "Neon Transit",
    artist: str | None = "Grid Runner",
    album: str | None = "Afterglow",
    beat_is_onset: bool | None = None,
    level_left: float | None = None,
    level_right: float | None = None,
    spectrum_bands: bytes | None = None,
) -> VisualizerFrameInput:
    return VisualizerFrameInput(
        frame_index=frame_index,
        monotonic_s=0.0,
        width=width,
        height=height,
        status="playing",
        position_s=2.0,
        duration_s=120.0,
        volume=60.0,
        speed=1.0,
        repeat_mode="OFF",
        shuffle=False,
        track_id=1,
        track_path="/tmp/music/signal-bloom.mp3",
        title=title,
        artist=artist,
        album=album,
        beat_is_onset=beat_is_onset,
        level_left=level_left,
        level_right=level_right,
        spectrum_bands=spectrum_bands,
    )


def test_typography_plugin_is_registered_built_in() -> None:
    registry = VisualizerRegistry.built_in()
    assert registry.has_plugin("viz.typography.glitch")


def test_typography_plugin_declares_beat_requirement() -> None:
    plugin = TypographyGlitchVisualizer()
    assert plugin.requires_beat is True


def test_typography_render_shows_metadata_lines() -> None:
    plugin = TypographyGlitchVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    output = plugin.render(
        _frame(
            width=40,
            height=7,
            beat_is_onset=False,
            level_left=0.55,
            level_right=0.45,
        )
    )
    assert "PLAYING | BEAT IDLE" in output
    assert "Neon Transit" in output
    assert "Grid Runner - Afterglow" in output


def test_typography_render_falls_back_to_track_name_when_metadata_missing() -> None:
    plugin = TypographyGlitchVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    output = plugin.render(
        _frame(
            width=42,
            height=7,
            title=None,
            artist=None,
            album=None,
            beat_is_onset=False,
        )
    )
    assert "signal-bloom.mp3" in output
    assert "Unknown Artist - Unknown Album" in output


def test_typography_beat_onset_triggers_visual_change() -> None:
    plugin = TypographyGlitchVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    base = plugin.render(_frame(width=40, height=7, frame_index=3, beat_is_onset=False))
    onset = plugin.render(
        _frame(
            width=40,
            height=7,
            frame_index=3,
            beat_is_onset=True,
            spectrum_bands=bytes([20, 30, 40, 50, 220, 240, 250, 255] * 6),
        )
    )
    assert base != onset
    assert "BEAT ONSET" in onset


def test_typography_render_is_deterministic_after_reactivation() -> None:
    plugin = TypographyGlitchVisualizer()
    context = VisualizerContext(ansi_enabled=False, unicode_enabled=True)
    frame = _frame(
        width=36,
        height=7,
        frame_index=9,
        beat_is_onset=True,
        level_left=0.6,
        level_right=0.7,
        spectrum_bands=bytes([10, 30, 60, 90, 120, 160, 210, 255] * 5),
    )
    plugin.on_activate(context)
    first = plugin.render(frame)
    plugin.on_deactivate()
    plugin.on_activate(context)
    assert first == plugin.render(frame)


def test_typography_ansi_output_stays_within_requested_width() -> None:
    plugin = TypographyGlitchVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=True, unicode_enabled=True))
    output = plugin.render(
        _frame(
            width=26,
            height=7,
            beat_is_onset=True,
            spectrum_bands=bytes([10, 20, 30, 50, 160, 180, 220, 255] * 4),
            level_left=0.75,
            level_right=0.70,
        )
    )
    assert "\x1b[38;2;" in output
    for line in output.splitlines():
        assert len(_SGR_PATTERN.sub("", line)) <= 26
