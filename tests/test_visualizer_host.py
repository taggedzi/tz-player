"""Tests for visualizer host lifecycle and fallback."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pytest

import tz_player.visualizers.host as host_module
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


@dataclass
class SpectrumPlugin:
    plugin_id: str = "spectrum"
    display_name: str = "spectrum"
    requires_spectrum: bool = True

    def on_activate(self, context: VisualizerContext) -> None:
        return None

    def on_deactivate(self) -> None:
        return None

    def render(self, frame: VisualizerFrameInput) -> str:
        return "ok"


@dataclass
class BeatPlugin:
    plugin_id: str = "beat"
    display_name: str = "beat"
    requires_beat: bool = True

    def on_activate(self, context: VisualizerContext) -> None:
        return None

    def on_deactivate(self) -> None:
        return None

    def render(self, frame: VisualizerFrameInput) -> str:
        return "ok"


@dataclass
class WaveformPlugin:
    plugin_id: str = "waveform"
    display_name: str = "waveform"
    requires_waveform: bool = True

    def on_activate(self, context: VisualizerContext) -> None:
        return None

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


def test_active_requires_spectrum_reflects_plugin_capability() -> None:
    registry = VisualizerRegistry({"spectrum": SpectrumPlugin}, default_id="spectrum")
    host = VisualizerHost(registry)
    context = VisualizerContext(ansi_enabled=True, unicode_enabled=True)
    host.activate("spectrum", context)
    assert host.active_requires_spectrum is True


def test_active_requires_spectrum_defaults_false_for_legacy_plugins() -> None:
    registry = VisualizerRegistry({"good": GoodPlugin}, default_id="good")
    host = VisualizerHost(registry)
    context = VisualizerContext(ansi_enabled=True, unicode_enabled=True)
    host.activate("good", context)
    assert host.active_requires_spectrum is False


def test_active_requires_beat_reflects_plugin_capability() -> None:
    registry = VisualizerRegistry({"beat": BeatPlugin}, default_id="beat")
    host = VisualizerHost(registry)
    context = VisualizerContext(ansi_enabled=True, unicode_enabled=True)
    host.activate("beat", context)
    assert host.active_requires_beat is True


def test_active_requires_beat_defaults_false_for_legacy_plugins() -> None:
    registry = VisualizerRegistry({"good": GoodPlugin}, default_id="good")
    host = VisualizerHost(registry)
    context = VisualizerContext(ansi_enabled=True, unicode_enabled=True)
    host.activate("good", context)
    assert host.active_requires_beat is False


def test_active_requires_waveform_reflects_plugin_capability() -> None:
    registry = VisualizerRegistry({"waveform": WaveformPlugin}, default_id="waveform")
    host = VisualizerHost(registry)
    context = VisualizerContext(ansi_enabled=True, unicode_enabled=True)
    host.activate("waveform", context)
    assert host.active_requires_waveform is True


def test_active_requires_waveform_defaults_false_for_legacy_plugins() -> None:
    registry = VisualizerRegistry({"good": GoodPlugin}, default_id="good")
    host = VisualizerHost(registry)
    context = VisualizerContext(ansi_enabled=True, unicode_enabled=True)
    host.activate("good", context)
    assert host.active_requires_waveform is False


def test_overrun_and_throttle_emit_observability_events(caplog, monkeypatch) -> None:
    caplog.set_level(logging.INFO, logger="tz_player.visualizers.host")
    registry = VisualizerRegistry({"good": GoodPlugin}, default_id="good")
    host = VisualizerHost(registry, target_fps=10)
    context = VisualizerContext(ansi_enabled=True, unicode_enabled=True)
    host.activate("good", context)

    moments = iter([0.0, 0.20, 1.0, 1.20, 2.0, 2.20])
    monkeypatch.setattr(host_module.time, "monotonic", lambda: next(moments))

    host.render_frame(_frame(), context)
    host.render_frame(_frame(), context)
    host.render_frame(_frame(), context)
    throttled = host.render_frame(_frame(), context)

    assert throttled == "Visualizer throttled"
    overrun_events = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "visualizer_render_overrun"
    ]
    assert len(overrun_events) >= 3
    throttle_events = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "visualizer_throttle_engaged"
    ]
    assert throttle_events
    skip_events = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "visualizer_throttle_skip"
    ]
    assert skip_events


def test_heavy_overrun_scales_throttle_frames(caplog, monkeypatch) -> None:
    caplog.set_level(logging.INFO, logger="tz_player.visualizers.host")
    registry = VisualizerRegistry({"good": GoodPlugin}, default_id="good")
    host = VisualizerHost(registry, target_fps=10)
    context = VisualizerContext(ansi_enabled=True, unicode_enabled=True)
    host.activate("good", context)

    # 0.45s render time against 0.1s budget => overrun ratio ~4.5 -> skip >= 3.
    moments = iter([0.0, 0.45, 1.0, 1.45, 2.0, 2.45])
    monkeypatch.setattr(host_module.time, "monotonic", lambda: next(moments))

    host.render_frame(_frame(), context)
    host.render_frame(_frame(), context)
    host.render_frame(_frame(), context)

    throttle_events = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "visualizer_throttle_engaged"
    ]
    assert throttle_events
    assert getattr(throttle_events[-1], "throttle_frames", 0) >= 3
