"""Tests for visualizer host lifecycle and fallback."""

from __future__ import annotations

from dataclasses import dataclass

from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.host import VisualizerHost
from tz_player.visualizers.registry import VisualizerRegistry


@dataclass
class GoodPlugin:
    plugin_id: str = "good"
    display_name: str = "good"

    def on_activate(self, context: VisualizerContext) -> None:
        return None

    def on_deactivate(self) -> None:
        return None

    def render(self, frame: VisualizerFrameInput) -> str:
        return "ok"


@dataclass
class BadRenderPlugin:
    plugin_id: str = "bad"
    display_name: str = "bad"

    def on_activate(self, context: VisualizerContext) -> None:
        return None

    def on_deactivate(self) -> None:
        return None

    def render(self, frame: VisualizerFrameInput) -> str:
        raise RuntimeError("boom")


def _frame() -> VisualizerFrameInput:
    return VisualizerFrameInput(
        frame_index=0,
        monotonic_s=0.0,
        width=20,
        height=3,
        status="playing",
        position_s=1.0,
        duration_s=10.0,
        volume=100.0,
        speed=1.0,
        repeat_mode="OFF",
        shuffle=False,
        track_id=None,
        track_path=None,
        title=None,
        artist=None,
        album=None,
    )


def test_activate_unknown_visualizer_falls_back_to_default() -> None:
    registry = VisualizerRegistry({"good": GoodPlugin}, default_id="good")
    host = VisualizerHost(registry)
    context = VisualizerContext(ansi_enabled=True, unicode_enabled=True)

    active = host.activate("missing", context)

    assert active == "good"
    assert host.active_id == "good"
    assert host.consume_notice() is not None


def test_render_failure_falls_back_to_default() -> None:
    registry = VisualizerRegistry(
        {"good": GoodPlugin, "bad": BadRenderPlugin},
        default_id="good",
    )
    host = VisualizerHost(registry)
    context = VisualizerContext(ansi_enabled=True, unicode_enabled=True)
    host.activate("bad", context)

    output = host.render_frame(_frame(), context)

    assert output == "ok"
    assert host.active_id == "good"
    assert host.consume_notice() is not None
