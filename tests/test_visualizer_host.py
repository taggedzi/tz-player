"""Tests for visualizer host lifecycle and fallback."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pytest

from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.host import VisualizerHost
from tz_player.visualizers.registry import VisualizerRegistry


@dataclass
class GoodPlugin:
    """Healthy plugin double used for baseline host behavior assertions."""

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
    """Plugin double that fails during render to test fallback path."""

    plugin_id: str = "bad"
    display_name: str = "bad"

    def on_activate(self, context: VisualizerContext) -> None:
        return None

    def on_deactivate(self) -> None:
        return None

    def render(self, frame: VisualizerFrameInput) -> str:
        raise RuntimeError("boom")


@dataclass
class BadActivatePlugin:
    """Plugin double that fails during activation to test hard failure path."""

    plugin_id: str = "bad-activate"
    display_name: str = "bad-activate"

    def on_activate(self, context: VisualizerContext) -> None:
        raise RuntimeError("activate boom")

    def on_deactivate(self) -> None:
        return None

    def render(self, frame: VisualizerFrameInput) -> str:
        return "ok"


def _frame() -> VisualizerFrameInput:
    """Build minimal frame payload for host-render tests."""
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


def test_render_failure_logs_fallback_transition(caplog) -> None:
    caplog.set_level(logging.INFO, logger="tz_player.visualizers.host")
    registry = VisualizerRegistry(
        {"good": GoodPlugin, "bad": BadRenderPlugin},
        default_id="good",
    )
    host = VisualizerHost(registry)
    context = VisualizerContext(ansi_enabled=True, unicode_enabled=True)
    host.activate("bad", context)

    host.render_frame(_frame(), context)

    fallback_events = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "visualizer_fallback"
    ]
    assert fallback_events
    event = fallback_events[-1]
    assert getattr(event, "phase", None) == "render"
    assert getattr(event, "requested_plugin_id", None) == "bad"
    assert getattr(event, "active_plugin_id", None) == "good"


def test_activate_raises_clear_error_when_fallback_activation_fails() -> None:
    registry = VisualizerRegistry(
        {"bad-activate": BadActivatePlugin},
        default_id="bad-activate",
    )
    host = VisualizerHost(registry)
    context = VisualizerContext(ansi_enabled=True, unicode_enabled=True)

    with pytest.raises(RuntimeError, match="Fallback visualizer activation failed"):
        host.activate("bad-activate", context)
