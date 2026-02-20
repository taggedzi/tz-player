"""Visualizer plugin discovery and factory registry.

The registry collects built-in plugins and optional local plugins, validates
plugin metadata, and exposes stable construction by ``plugin_id``.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import inspect
import logging
import os
import pkgutil
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from .base import VisualizerPlugin
from .basic import BasicVisualizer
from .cover_ascii import CoverAsciiMotionVisualizer, CoverAsciiStaticVisualizer
from .hackscope import HackScopeVisualizer
from .matrix import MatrixBlueVisualizer, MatrixGreenVisualizer, MatrixRedVisualizer
from .vu import VuReactiveVisualizer

logger = logging.getLogger(__name__)

PluginFactory = Callable[[], VisualizerPlugin]
PLUGIN_API_VERSION = 1
_SECURITY_MODES = {"off", "warn", "enforce"}
_DENY_IMPORT_ENV = "TZ_PLAYER_VIS_PLUGIN_DENY_IMPORT_PREFIXES"
_ALLOW_IMPORT_ENV = "TZ_PLAYER_VIS_PLUGIN_ALLOW_IMPORT_PREFIXES"
_MODULE_NAME_RE = re.compile(r"^[A-Za-z0-9_.]+$")

_RISKY_IMPORT_PREFIXES = (
    "subprocess",
    "socket",
    "http",
    "urllib",
    "ftplib",
    "telnetlib",
)
_RISKY_CALL_PREFIXES = (
    "subprocess.",
    "socket.",
    "requests.",
    "http.",
    "urllib.",
)
_RISKY_CALL_NAMES = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "os.system",
    "os.remove",
    "os.rmdir",
    "os.unlink",
    "shutil.rmtree",
    "Path.unlink",
    "Path.rmdir",
}


@dataclass
class _DiscoveryContext:
    mode: str
    notices: list[str]
    allow_import_prefixes: tuple[str, ...]
    deny_import_prefixes: tuple[str, ...]


class VisualizerRegistry:
    """Registry for discovering and creating visualizer plugins by stable ID."""

    def __init__(
        self,
        factories: dict[str, PluginFactory],
        default_id: str,
        *,
        notices: list[str] | None = None,
    ) -> None:
        if not factories:
            raise ValueError("VisualizerRegistry requires at least one plugin factory.")
        if default_id not in factories:
            raise ValueError(
                f"VisualizerRegistry default_id '{default_id}' is not registered."
            )
        self._factories = factories
        self._default_id = default_id
        self._notices = notices or []

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

    def consume_notices(self) -> list[str]:
        notices = self._notices[:]
        self._notices.clear()
        return notices

    @classmethod
    def built_in(
        cls,
        *,
        local_plugin_paths: list[str] | None = None,
        plugin_security_mode: str = "warn",
    ) -> VisualizerRegistry:
        plugin_types: list[type[VisualizerPlugin]] = [
            BasicVisualizer,
            MatrixGreenVisualizer,
            MatrixBlueVisualizer,
            MatrixRedVisualizer,
            HackScopeVisualizer,
            VuReactiveVisualizer,
            CoverAsciiStaticVisualizer,
            CoverAsciiMotionVisualizer,
        ]
        context = _make_discovery_context(plugin_security_mode)
        if local_plugin_paths:
            plugin_types.extend(
                _discover_local_plugin_types(local_plugin_paths, context)
            )
        factories = _build_factory_map(plugin_types)
        default_id = "basic"
        if default_id not in factories:
            msg = "Built-in visualizers missing required 'basic' plugin."
            raise RuntimeError(msg)
        logger.info(
            "Visualizer registry loaded",
            extra={
                "event": "visualizer_registry_loaded",
                "plugin_count": len(factories),
                "plugin_ids": sorted(factories),
                "local_plugin_paths": local_plugin_paths or [],
                "default_id": default_id,
                "plugin_security_mode": context.mode,
                "plugin_notices": context.notices,
            },
        )
        return cls(factories, default_id=default_id, notices=context.notices)


def _make_discovery_context(plugin_security_mode: str) -> _DiscoveryContext:
    mode = plugin_security_mode.strip().lower()
    notices: list[str] = []
    if mode not in _SECURITY_MODES:
        mode = "warn"
        notices.append("Invalid visualizer plugin security mode; using 'warn'.")
        logger.warning(
            "Unknown plugin security mode '%s'; defaulting to 'warn'.",
            plugin_security_mode,
        )
    allow_prefixes = _parse_env_prefixes(_ALLOW_IMPORT_ENV)
    deny_prefixes = _parse_env_prefixes(_DENY_IMPORT_ENV)
    return _DiscoveryContext(
        mode=mode,
        notices=notices,
        allow_import_prefixes=allow_prefixes,
        deny_import_prefixes=deny_prefixes,
    )


def _parse_env_prefixes(name: str) -> tuple[str, ...]:
    raw = os.getenv(name, "")
    parts = [part.strip() for part in raw.split(",")]
    return tuple(part for part in parts if part)


def _discover_local_plugin_types(
    import_paths: list[str],
    context: _DiscoveryContext,
) -> list[type[VisualizerPlugin]]:
    """Discover plugin classes from configured file/module import entries."""
    plugin_types: list[type[VisualizerPlugin]] = []
    seen: set[type[VisualizerPlugin]] = set()
    for entry in import_paths:
        for module in _load_modules_from_entry(entry, context):
            for candidate in _extract_plugin_types(module):
                if candidate in seen:
                    continue
                seen.add(candidate)
                plugin_types.append(candidate)
    return plugin_types


def _load_modules_from_entry(
    entry: str, context: _DiscoveryContext
) -> list[ModuleType]:
    """Load modules from filesystem path or import path entry."""
    path = Path(entry)
    modules: list[ModuleType] = []
    if path.exists():
        if path.is_file() and path.suffix.lower() == ".py":
            module = _load_module_from_file(path, context)
            if module is not None:
                modules.append(module)
            return modules
        if path.is_dir():
            if (path / "__init__.py").exists():
                package = _load_module_from_package_dir(path, context)
                if package is not None:
                    modules.append(package)
                    modules.extend(_load_package_children(package, context))
                return modules
            for child in sorted(path.iterdir()):
                if child.name.startswith("_"):
                    continue
                if child.is_file() and child.suffix.lower() == ".py":
                    module = _load_module_from_file(child, context)
                    if module is not None:
                        modules.append(module)
                elif child.is_dir() and (child / "__init__.py").exists():
                    package = _load_module_from_package_dir(child, context)
                    if package is not None:
                        modules.append(package)
                        modules.extend(_load_package_children(package, context))
            return modules
        logger.error(
            "Visualizer plugin path '%s' is neither a Python file nor a directory.",
            entry,
        )
        return modules

    if not _is_safe_module_entry(entry):
        message = f"Rejected invalid visualizer module path '{entry}'."
        logger.error(message)
        context.notices.append(message)
        return modules
    module = _load_module_from_import(entry, context)
    if module is None:
        return modules
    modules.append(module)
    module_path = getattr(module, "__path__", None)
    if module_path is not None:
        modules.extend(_load_package_children(module, context))
    return modules


def _load_package_children(
    package: ModuleType,
    context: _DiscoveryContext,
) -> list[ModuleType]:
    children: list[ModuleType] = []
    module_path = getattr(package, "__path__", None)
    if module_path is None:
        return children
    prefix = f"{package.__name__}."
    for module_info in pkgutil.iter_modules(module_path, prefix):
        child = _load_module_from_import(module_info.name, context)
        if child is not None:
            children.append(child)
    return children


def _load_module_from_import(
    module_name: str,
    context: _DiscoveryContext,
) -> ModuleType | None:
    """Import a module path and return ``None`` on failure with logged context."""
    if not _module_allowed(module_name, context):
        return None
    try:
        spec = importlib.util.find_spec(module_name)
    except Exception as exc:
        logger.error(
            "Failed to import visualizer plugin module '%s': %s", module_name, exc
        )
        return None
    if spec is not None and spec.origin and spec.origin.endswith(".py"):
        source_path = Path(spec.origin)
        if not _preflight_plugin_source(source_path, context):
            return None
    try:
        return importlib.import_module(module_name)
    except Exception as exc:
        logger.error(
            "Failed to import visualizer plugin module '%s': %s", module_name, exc
        )
        return None


def _load_module_from_package_dir(
    package_dir: Path,
    context: _DiscoveryContext,
) -> ModuleType | None:
    """Load package directory as isolated runtime package for plugin discovery."""
    init_file = package_dir / "__init__.py"
    if not _preflight_plugin_source(init_file, context):
        return None
    module_name = f"tz_player.user_visualizer_pkg_{abs(hash(str(package_dir)))}"
    try:
        spec = importlib.util.spec_from_file_location(
            module_name,
            init_file,
            submodule_search_locations=[str(package_dir)],
        )
        if spec is None or spec.loader is None:
            logger.error(
                "Failed to create module spec for visualizer package '%s'.", package_dir
            )
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    except Exception as exc:
        logger.error("Failed to import visualizer package '%s': %s", package_dir, exc)
        return None


def _load_module_from_file(path: Path, context: _DiscoveryContext) -> ModuleType | None:
    """Load a Python file as an isolated runtime module for plugin discovery."""
    if not _preflight_plugin_source(path, context):
        return None
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


def _preflight_plugin_source(path: Path, context: _DiscoveryContext) -> bool:
    """Run static risk checks for plugin source based on configured policy."""
    if context.mode == "off":
        return True
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Unable to read visualizer plugin source '%s': %s", path, exc)
        return False
    findings = _scan_source_for_risky_ops(path, source)
    if not findings:
        return True
    summary = f"Visualizer plugin source '{path}' contains risky operations."
    details = "; ".join(findings)
    if context.mode == "enforce":
        logger.error("%s Blocking load: %s", summary, details)
        context.notices.append(f"Blocked plugin '{path.name}' by security policy.")
        return False
    logger.warning("%s Loading with warning: %s", summary, details)
    context.notices.append(f"Plugin '{path.name}' loaded with security warnings.")
    return True


def _scan_source_for_risky_ops(path: Path, source: str) -> list[str]:
    findings: list[str] = []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        # Syntax issues are handled during import; this scanner only reports risk.
        return findings

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _starts_with_prefix(alias.name, _RISKY_IMPORT_PREFIXES):
                    findings.append(f"import:{alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if _starts_with_prefix(module, _RISKY_IMPORT_PREFIXES):
                findings.append(f"import:{module}")
        elif isinstance(node, ast.Call):
            call_name = _call_name(node.func)
            if call_name in _RISKY_CALL_NAMES:
                findings.append(f"call:{call_name}")
            if _starts_with_prefix(call_name, _RISKY_CALL_PREFIXES):
                findings.append(f"call:{call_name}")
            if call_name == "open" and _open_call_is_write(node):
                findings.append("call:open(write)")

    # Keep diagnostics short and deterministic.
    deduped = sorted(set(findings))
    return deduped[:10]


def _open_call_is_write(node: ast.Call) -> bool:
    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
        mode = node.args[1].value
        if isinstance(mode, str) and any(token in mode for token in ("w", "a", "+")):
            return True
    for keyword in node.keywords:
        if keyword.arg != "mode":
            continue
        if isinstance(keyword.value, ast.Constant) and isinstance(
            keyword.value.value, str
        ):
            mode = keyword.value.value
            if any(token in mode for token in ("w", "a", "+")):
                return True
    return False


def _call_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parts: list[str] = [func.attr]
        current = func.value
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        parts.reverse()
        return ".".join(parts)
    return ""


def _module_allowed(module_name: str, context: _DiscoveryContext) -> bool:
    for blocked in context.deny_import_prefixes:
        if module_name == blocked or module_name.startswith(f"{blocked}."):
            logger.error(
                "Visualizer plugin module '%s' blocked by denylist prefix '%s'.",
                module_name,
                blocked,
            )
            context.notices.append(
                f"Blocked plugin module '{module_name}' by import denylist."
            )
            return False
    if context.allow_import_prefixes:
        for allowed in context.allow_import_prefixes:
            if module_name == allowed or module_name.startswith(f"{allowed}."):
                return True
        logger.error(
            "Visualizer plugin module '%s' not in allowlist; skipping.", module_name
        )
        context.notices.append(
            f"Skipped plugin module '{module_name}' (not in allowlist)."
        )
        return False
    return True


def _is_safe_module_entry(entry: str) -> bool:
    if not _MODULE_NAME_RE.fullmatch(entry):
        return False
    return ".." not in entry


def _starts_with_prefix(name: str, prefixes: tuple[str, ...]) -> bool:
    if not name:
        return False
    return any(name == prefix or name.startswith(f"{prefix}.") for prefix in prefixes)


def _extract_plugin_types(module: ModuleType) -> list[type[VisualizerPlugin]]:
    """Extract candidate plugin classes from a loaded module namespace."""
    plugin_types: list[type[VisualizerPlugin]] = []
    for value in vars(module).values():
        if not inspect.isclass(value):
            continue
        if _looks_like_plugin_type(value):
            plugin_types.append(value)
    return plugin_types


def _looks_like_plugin_type(candidate: type[object]) -> bool:
    """Heuristic check for classes matching the visualizer plugin contract."""
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
    """Instantiate plugin classes once to validate and index by stable ID."""
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
        display_name = getattr(sample, "display_name", None)
        if not isinstance(display_name, str) or not display_name.strip():
            logger.error("Visualizer plugin %s has invalid display_name", plugin_type)
            continue
        api_version = getattr(sample, "plugin_api_version", None)
        if api_version != PLUGIN_API_VERSION:
            logger.error(
                "Visualizer plugin %s has incompatible plugin_api_version '%s' (expected %s)",
                plugin_type,
                api_version,
                PLUGIN_API_VERSION,
            )
            continue
        if plugin_id in factories:
            logger.error(
                "Duplicate visualizer plugin_id '%s'; keeping first plugin", plugin_id
            )
            continue
        factories[plugin_id] = plugin_type
    return factories
