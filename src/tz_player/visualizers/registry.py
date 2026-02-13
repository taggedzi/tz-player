"""Visualizer plugin registry."""

from __future__ import annotations

import logging
from collections.abc import Callable

from .base import VisualizerPlugin
from .basic import BasicVisualizer
from .matrix import MatrixBlueVisualizer, MatrixGreenVisualizer, MatrixRedVisualizer

logger = logging.getLogger(__name__)

PluginFactory = Callable[[], VisualizerPlugin]


class VisualizerRegistry:
    """Registry for discovering and creating visualizer plugins by stable ID."""

    def __init__(self, factories: dict[str, PluginFactory], default_id: str) -> None:
        self._factories = factories
        self._default_id = default_id

    @property
    def default_id(self) -> str:
        return self._default_id

    def plugin_ids(self) -> list[str]:
        return sorted(self._factories)

    def has_plugin(self, plugin_id: str) -> bool:
        return plugin_id in self._factories

    def create(self, plugin_id: str) -> VisualizerPlugin | None:
        factory = self._factories.get(plugin_id)
        if factory is None:
            return None
        return factory()

    @classmethod
    def built_in(cls) -> VisualizerRegistry:
        factories = _build_factory_map(
            [
                BasicVisualizer,
                MatrixGreenVisualizer,
                MatrixBlueVisualizer,
                MatrixRedVisualizer,
            ]
        )
        default_id = "basic"
        if default_id not in factories:
            msg = "Built-in visualizers missing required 'basic' plugin."
            raise RuntimeError(msg)
        return cls(factories, default_id=default_id)


def _build_factory_map(
    plugin_types: list[type[VisualizerPlugin]],
) -> dict[str, PluginFactory]:
    factories: dict[str, PluginFactory] = {}
    for plugin_type in plugin_types:
        try:
            sample = plugin_type()
        except Exception as exc:
            logger.error(
                "Failed to instantiate visualizer plugin %s: %s", plugin_type, exc
            )
            continue
        plugin_id = getattr(sample, "plugin_id", None)
        if not isinstance(plugin_id, str) or not plugin_id.strip():
            logger.error("Visualizer plugin %s has invalid plugin_id", plugin_type)
            continue
        if plugin_id in factories:
            logger.error(
                "Duplicate visualizer plugin_id '%s'; keeping first plugin", plugin_id
            )
            continue
        factories[plugin_id] = plugin_type
    return factories
