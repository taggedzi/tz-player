"""Tests for HackScope visualizer plugin."""

from __future__ import annotations

from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.hackscope import HackScopeVisualizer
from tz_player.visualizers.registry import VisualizerRegistry


def _frame(
    *,
    width: int,
    height: int,
    frame_index: int = 0,
    status: str = "playing",
) -> VisualizerFrameInput:
    """Build deterministic frame payload for HackScope render tests."""
    return VisualizerFrameInput(
        frame_index=frame_index,
        monotonic_s=0.0,
        width=width,
        height=height,
        status=status,
        position_s=12.0,
        duration_s=200.0,
        volume=73.0,
        speed=1.0,
        repeat_mode="OFF",
        shuffle=False,
        track_id=1,
        track_path="/tmp/track.mp3",
        title="Neon Shadow",
        artist="Proxy Unit",
        album="Gridline",
    )


def test_hackscope_plugin_is_registered_built_in() -> None:
    registry = VisualizerRegistry.built_in()
    assert registry.has_plugin("ops.hackscope")


def test_hackscope_render_contains_header_and_stage_output() -> None:
    plugin = HackScopeVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    output = plugin.render(_frame(width=70, height=10, frame_index=0))
    assert "[HackScope]" in output
    assert "BOOT" in output


def test_hackscope_render_is_deterministic_for_same_frame() -> None:
    plugin = HackScopeVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    frame = _frame(width=70, height=12, frame_index=42)
    assert plugin.render(frame) == plugin.render(frame)


def test_hackscope_render_respects_resize_bounds() -> None:
    plugin = HackScopeVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    output = plugin.render(_frame(width=20, height=4, frame_index=10))
    lines = output.splitlines()
    assert len(lines) == 4
    assert all(len(line) <= 20 for line in lines)


def test_hackscope_render_idle_when_not_playing() -> None:
    plugin = HackScopeVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    output = plugin.render(_frame(width=60, height=8, status="stopped"))
    assert "IDLE" in output
    assert "waiting for active playback stream" in output


def test_hackscope_ansi_output_has_no_partial_escape_sequences() -> None:
    plugin = HackScopeVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=True, unicode_enabled=True))
    output = plugin.render(_frame(width=70, height=12, frame_index=31))
    for line in output.splitlines():
        cleaned = line
        while "\x1b[" in cleaned:
            start = cleaned.find("\x1b[")
            end = cleaned.find("m", start + 2)
            assert end != -1
            cleaned = cleaned[:start] + cleaned[end + 1 :]


def test_hackscope_handles_non_finite_duration_without_crash() -> None:
    plugin = HackScopeVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    frame = _frame(width=70, height=12, frame_index=84)
    frame = VisualizerFrameInput(
        frame_index=frame.frame_index,
        monotonic_s=frame.monotonic_s,
        width=frame.width,
        height=frame.height,
        status=frame.status,
        position_s=frame.position_s,
        duration_s=float("nan"),
        volume=frame.volume,
        speed=frame.speed,
        repeat_mode=frame.repeat_mode,
        shuffle=frame.shuffle,
        track_id=frame.track_id,
        track_path=frame.track_path,
        title=frame.title,
        artist=frame.artist,
        album=frame.album,
    )
    output = plugin.render(frame)
    assert "Unknown" in output
