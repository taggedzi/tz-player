"""Tests for visualizer registry behavior."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pytest

from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.registry import VisualizerRegistry, _build_factory_map


@dataclass
class FirstPlugin:
    """Duplicate-id plugin candidate used to assert first-registration wins."""

    plugin_id: str = "dup"
    display_name: str = "first"
    plugin_api_version: int = 1

    def on_activate(self, context: VisualizerContext) -> None:
        return None

    def on_deactivate(self) -> None:
        return None

    def render(self, frame: VisualizerFrameInput) -> str:
        return "first"


@dataclass
class SecondPlugin:
    """Second duplicate-id candidate expected to be ignored by registry."""

    plugin_id: str = "dup"
    display_name: str = "second"
    plugin_api_version: int = 1

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


def test_local_plugin_discovery_from_directory(tmp_path: Path) -> None:
    plugin_file = tmp_path / "my_plugin.py"
    plugin_file.write_text(
        """
class LocalViz:
    plugin_id = "local.demo"
    display_name = "Local Demo"
    plugin_api_version = 1

    def on_activate(self, context):
        return None

    def on_deactivate(self):
        return None

    def render(self, frame):
        return "local"
""".strip(),
        encoding="utf-8",
    )
    registry = VisualizerRegistry.built_in(local_plugin_paths=[str(tmp_path)])
    assert registry.has_plugin("local.demo")
    plugin = registry.create("local.demo")
    assert plugin is not None
    assert plugin.plugin_id == "local.demo"


def test_local_duplicate_id_does_not_override_built_in(tmp_path: Path) -> None:
    plugin_file = tmp_path / "dup_basic.py"
    plugin_file.write_text(
        """
class DuplicateBasic:
    plugin_id = "basic"
    display_name = "Override Basic"
    plugin_api_version = 1

    def on_activate(self, context):
        return None

    def on_deactivate(self):
        return None

    def render(self, frame):
        return "override"
""".strip(),
        encoding="utf-8",
    )
    registry = VisualizerRegistry.built_in(local_plugin_paths=[str(tmp_path)])
    plugin = registry.create("basic")
    assert plugin is not None
    assert plugin.display_name != "Override Basic"


def test_registry_logs_load_summary(caplog) -> None:
    caplog.set_level(logging.INFO, logger="tz_player.visualizers.registry")
    VisualizerRegistry.built_in()
    events = [
        record
        for record in caplog.records
        if record.msg == "Visualizer registry loaded"
    ]
    assert events
    record = events[-1]
    assert getattr(record, "event", None) == "visualizer_registry_loaded"
    assert isinstance(getattr(record, "plugin_ids", None), list)


def test_registry_requires_registered_default_id() -> None:
    with pytest.raises(ValueError, match="default_id 'missing' is not registered"):
        VisualizerRegistry({"dup": FirstPlugin}, default_id="missing")


def test_local_package_plugin_discovery_from_directory(tmp_path: Path) -> None:
    package_dir = tmp_path / "demo_pkg"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text(
        """
from .impl import PackageViz
""".strip(),
        encoding="utf-8",
    )
    (package_dir / "impl.py").write_text(
        """
class PackageViz:
    plugin_id = "local.package"
    display_name = "Local Package"
    plugin_api_version = 1

    def on_activate(self, context):
        return None

    def on_deactivate(self):
        return None

    def render(self, frame):
        return "package"
""".strip(),
        encoding="utf-8",
    )
    registry = VisualizerRegistry.built_in(local_plugin_paths=[str(tmp_path)])
    assert registry.has_plugin("local.package")


def test_registry_rejects_incompatible_plugin_api_version(tmp_path: Path) -> None:
    plugin_file = tmp_path / "bad_api.py"
    plugin_file.write_text(
        """
class BadApiPlugin:
    plugin_id = "local.bad-api"
    display_name = "Bad API"
    plugin_api_version = 99

    def on_activate(self, context):
        return None

    def on_deactivate(self):
        return None

    def render(self, frame):
        return "bad"
""".strip(),
        encoding="utf-8",
    )
    registry = VisualizerRegistry.built_in(local_plugin_paths=[str(tmp_path)])
    assert not registry.has_plugin("local.bad-api")


def test_registry_enforce_mode_blocks_risky_plugin(tmp_path: Path) -> None:
    plugin_file = tmp_path / "risky.py"
    plugin_file.write_text(
        """
import subprocess

class RiskyViz:
    plugin_id = "local.risky"
    display_name = "Risky"
    plugin_api_version = 1

    def on_activate(self, context):
        return None

    def on_deactivate(self):
        return None

    def render(self, frame):
        return "risky"
""".strip(),
        encoding="utf-8",
    )
    registry = VisualizerRegistry.built_in(
        local_plugin_paths=[str(tmp_path)],
        plugin_security_mode="enforce",
    )
    assert not registry.has_plugin("local.risky")
    notices = registry.consume_notices()
    assert any("Blocked plugin" in notice for notice in notices)
