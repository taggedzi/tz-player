"""Visualizer plugin registry."""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import pkgutil
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

from .base import VisualizerPlugin
from .basic import BasicVisualizer
from .hackscope import HackScopeVisualizer
from .matrix import MatrixBlueVisualizer, MatrixGreenVisualizer, MatrixRedVisualizer
from .vu import VuReactiveVisualizer

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
    def built_in(
        cls, *, local_plugin_paths: list[str] | None = None
    ) -> VisualizerRegistry:
        plugin_types: list[type[VisualizerPlugin]] = [
            BasicVisualizer,
            MatrixGreenVisualizer,
            MatrixBlueVisualizer,
            MatrixRedVisualizer,
            HackScopeVisualizer,
            VuReactiveVisualizer,
        ]
        if local_plugin_paths:
            plugin_types.extend(_discover_local_plugin_types(local_plugin_paths))
        factories = _build_factory_map(plugin_types)
        default_id = "basic"
        if default_id not in factories:
            msg = "Built-in visualizers missing required 'basic' plugin."
            raise RuntimeError(msg)
        return cls(factories, default_id=default_id)


def _discover_local_plugin_types(
    import_paths: list[str],
) -> list[type[VisualizerPlugin]]:
    plugin_types: list[type[VisualizerPlugin]] = []
    seen: set[type[VisualizerPlugin]] = set()
    for entry in import_paths:
        for module in _load_modules_from_entry(entry):
            for candidate in _extract_plugin_types(module):
                if candidate in seen:
                    continue
                seen.add(candidate)
                plugin_types.append(candidate)
    return plugin_types


def _load_modules_from_entry(entry: str) -> list[ModuleType]:
    path = Path(entry)
    modules: list[ModuleType] = []
    if path.exists():
        if path.is_file() and path.suffix.lower() == ".py":
            module = _load_module_from_file(path)
            if module is not None:
                modules.append(module)
            return modules
        if path.is_dir():
            for py_file in sorted(path.glob("*.py")):
                if py_file.name.startswith("_"):
                    continue
                module = _load_module_from_file(py_file)
                if module is not None:
                    modules.append(module)
            return modules
        logger.error(
            "Visualizer plugin path '%s' is neither a Python file nor a directory.",
            entry,
        )
        return modules
    module = _load_module_from_import(entry)
    if module is None:
        return modules
    modules.append(module)
    module_path = getattr(module, "__path__", None)
    if module_path is not None:
        prefix = f"{module.__name__}."
        for module_info in pkgutil.iter_modules(module_path, prefix):
            child = _load_module_from_import(module_info.name)
            if child is not None:
                modules.append(child)
    return modules


def _load_module_from_import(module_name: str) -> ModuleType | None:
    try:
        return importlib.import_module(module_name)
    except Exception as exc:
        logger.error(
            "Failed to import visualizer plugin module '%s': %s", module_name, exc
        )
        return None


def _load_module_from_file(path: Path) -> ModuleType | None:
    module_name = f"tz_player.user_visualizer_{abs(hash(str(path)))}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            logger.error("Failed to create module spec for visualizer file '%s'.", path)
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    except Exception as exc:
        logger.error("Failed to import visualizer plugin file '%s': %s", path, exc)
        return None


def _extract_plugin_types(module: ModuleType) -> list[type[VisualizerPlugin]]:
    plugin_types: list[type[VisualizerPlugin]] = []
    for value in vars(module).values():
        if not inspect.isclass(value):
            continue
        if _looks_like_plugin_type(value):
            plugin_types.append(value)
    return plugin_types


def _looks_like_plugin_type(candidate: type[object]) -> bool:
    if getattr(candidate, "__module__", "").startswith("typing"):
        return False
    if not hasattr(candidate, "plugin_id"):
        return False
    has_render = callable(getattr(candidate, "render", None))
    has_activate = callable(getattr(candidate, "on_activate", None))
    has_deactivate = callable(getattr(candidate, "on_deactivate", None))
    return has_render and has_activate and has_deactivate


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
