"""Tests for visualizer registry behavior."""

from __future__ import annotations

from dataclasses import dataclass

from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.registry import VisualizerRegistry, _build_factory_map


@dataclass
class FirstPlugin:
    plugin_id: str = "dup"
    display_name: str = "first"

    def on_activate(self, context: VisualizerContext) -> None:
        return None

    def on_deactivate(self) -> None:
        return None

    def render(self, frame: VisualizerFrameInput) -> str:
        return "first"


@dataclass
class SecondPlugin:
    plugin_id: str = "dup"
    display_name: str = "second"

    def on_activate(self, context: VisualizerContext) -> None:
        return None

    def on_deactivate(self) -> None:
        return None

    def render(self, frame: VisualizerFrameInput) -> str:
        return "second"


def test_built_in_registry_includes_basic() -> None:
    registry = VisualizerRegistry.built_in()
    assert registry.default_id == "basic"
    assert registry.has_plugin("basic")
    plugin = registry.create("basic")
    assert plugin is not None
    assert plugin.plugin_id == "basic"


def test_duplicate_plugin_id_keeps_first_factory() -> None:
    factories = _build_factory_map([FirstPlugin, SecondPlugin])
    assert list(factories) == ["dup"]
    plugin = factories["dup"]()
    assert plugin.display_name == "first"
