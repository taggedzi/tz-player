"""Integration tests for visualizer selection and persistence."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import tz_player.app as app_module
import tz_player.paths as paths
from tz_player.app import TzPlayerApp
from tz_player.state_store import AppState, load_state, save_state
from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.registry import VisualizerRegistry


class FakeAppDirs:
    """Path-dir stub for routing state/db paths into temporary test dirs."""

    def __init__(self, data_dir: Path, config_dir: Path) -> None:
        self.user_data_dir = str(data_dir)
        self.user_config_dir = str(config_dir)


def _run(coro):
    """Run async app scenario from sync test case."""
    return asyncio.run(coro)


def _setup_dirs(tmp_path, monkeypatch) -> None:
    """Patch `AppDirs` usage so persisted state is test-local."""
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"

    def fake_app_dirs(app_name: str, appauthor: bool | None = None) -> FakeAppDirs:
        return FakeAppDirs(data_dir, config_dir)

    monkeypatch.setattr(paths, "AppDirs", fake_app_dirs)
    paths.get_app_dirs.cache_clear()


def _stub_registry_built_in(monkeypatch, registry: VisualizerRegistry) -> None:
    """Patch registry factory to return a deterministic test registry."""

    def _built_in(
        cls,
        *,
        local_plugin_paths=None,
        plugin_security_mode="warn",
        plugin_runtime_mode="in-process",
    ):
        return registry

    monkeypatch.setattr(
        app_module.VisualizerRegistry,
        "built_in",
        classmethod(_built_in),
    )


@dataclass
class VizOne:
    """Visualizer stub representing first selectable plugin."""

    plugin_id: str = "viz.one"
    display_name: str = "Viz One"

    def on_activate(self, context: VisualizerContext) -> None:
        return None

    def on_deactivate(self) -> None:
        return None

    def render(self, frame: VisualizerFrameInput) -> str:
        return "one"


@dataclass
class VizTwo:
    """Visualizer stub representing second selectable plugin."""

    plugin_id: str = "viz.two"
    display_name: str = "Viz Two"

    def on_activate(self, context: VisualizerContext) -> None:
        return None

    def on_deactivate(self) -> None:
        return None

    def render(self, frame: VisualizerFrameInput) -> str:
        return "two"


@dataclass
class VizDefault:
    """Visualizer stub used as deterministic registry default."""

    plugin_id: str = "viz.default"
    display_name: str = "Viz Default"

    def on_activate(self, context: VisualizerContext) -> None:
        return None

    def on_deactivate(self) -> None:
        return None

    def render(self, frame: VisualizerFrameInput) -> str:
        return "default"


@dataclass
class VizAnsi:
    """Visualizer stub returning ANSI output for markup-safety regression."""

    plugin_id: str = "viz.ansi"
    display_name: str = "Viz ANSI"

    def on_activate(self, context: VisualizerContext) -> None:
        return None

    def on_deactivate(self) -> None:
        return None

    def render(self, frame: VisualizerFrameInput) -> str:
        return "\x1b[1;92mANSI\x1b[0m"


@dataclass
class VizSpectrum:
    """Visualizer stub opting into spectrum sampling capability."""

    plugin_id: str = "viz.spectrum"
    display_name: str = "Viz Spectrum"
    requires_spectrum: bool = True

    def on_activate(self, context: VisualizerContext) -> None:
        return None

    def on_deactivate(self) -> None:
        return None

    def render(self, frame: VisualizerFrameInput) -> str:
        return "spectrum"


def test_visualizer_selection_persists_across_restart(tmp_path, monkeypatch) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    registry = VisualizerRegistry(
        {"viz.one": VizOne, "viz.two": VizTwo},
        default_id="viz.one",
    )
    _stub_registry_built_in(monkeypatch, registry)

    app1 = TzPlayerApp(auto_init=False, backend_name="fake")

    async def run_first() -> None:
        async with app1.run_test() as pilot:
            await asyncio.sleep(0)
            await app1._initialize_state()
            assert app1.visualizer_host is not None
            assert app1.visualizer_host.active_id == "viz.one"

            await pilot.press("z")
            await asyncio.sleep(0)
            assert app1.visualizer_host.active_id == "viz.two"
            assert app1.state.visualizer_id == "viz.two"
            app1.exit()

    _run(run_first())

    persisted = load_state(paths.state_path())
    assert persisted.visualizer_id == "viz.two"

    app2 = TzPlayerApp(auto_init=False, backend_name="fake")

    async def run_second() -> None:
        async with app2.run_test():
            await asyncio.sleep(0)
            await app2._initialize_state()
            assert app2.visualizer_host is not None
            assert app2.visualizer_host.active_id == "viz.two"
            assert app2.state.visualizer_id == "viz.two"
            app2.exit()

    _run(run_second())


def test_unknown_persisted_visualizer_falls_back_and_repersists(
    tmp_path, monkeypatch
) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    registry = VisualizerRegistry(
        {"viz.default": VizDefault},
        default_id="viz.default",
    )
    _stub_registry_built_in(monkeypatch, registry)

    save_state(
        paths.state_path(),
        AppState(visualizer_id="viz.missing", playback_backend="fake"),
    )

    app = TzPlayerApp(auto_init=False, backend_name="fake")

    async def run_app() -> None:
        async with app.run_test():
            await asyncio.sleep(0)
            await app._initialize_state()
            assert app.visualizer_host is not None
            assert app.visualizer_host.active_id == "viz.default"
            assert app.state.visualizer_id == "viz.default"
            app.exit()

    _run(run_app())

    persisted = load_state(paths.state_path())
    assert persisted.visualizer_id == "viz.default"


def test_ansi_visualizer_output_does_not_raise_markup_error(
    tmp_path, monkeypatch
) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    registry = VisualizerRegistry(
        {"viz.default": VizDefault, "viz.ansi": VizAnsi},
        default_id="viz.default",
    )
    _stub_registry_built_in(monkeypatch, registry)
    app = TzPlayerApp(auto_init=False, backend_name="fake")

    async def run_app() -> None:
        async with app.run_test() as pilot:
            await asyncio.sleep(0)
            await app._initialize_state()
            assert app.visualizer_host is not None
            assert app.visualizer_host.active_id == "viz.default"
            await pilot.press("z")
            await asyncio.sleep(0)
            assert app.visualizer_host.active_id == "viz.ansi"
            app.exit()

    _run(run_app())


def test_startup_continues_when_local_visualizer_import_fails(
    tmp_path, monkeypatch, caplog
) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    save_state(
        paths.state_path(),
        AppState(
            playback_backend="fake",
            visualizer_plugin_paths=("does.not.exist.visualizers",),
        ),
    )
    app = TzPlayerApp(auto_init=False, backend_name="fake")

    async def run_app() -> None:
        async with app.run_test():
            await asyncio.sleep(0)
            await app._initialize_state()
            assert app.visualizer_host is not None
            assert app.visualizer_host.active_id == "basic"
            app.exit()

    _run(run_app())
    assert any(
        "Failed to import visualizer plugin module 'does.not.exist.visualizers'"
        in record.message
        for record in caplog.records
    )


def test_invalid_persisted_visualizer_fps_recovers_to_default(
    tmp_path, monkeypatch
) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    save_state(
        paths.state_path(),
        AppState(playback_backend="fake", visualizer_fps=99),
    )
    app = TzPlayerApp(auto_init=False, backend_name="fake")

    async def run_app() -> None:
        async with app.run_test():
            await asyncio.sleep(0)
            await app._initialize_state()
            assert app.visualizer_host is not None
            assert app.visualizer_host.target_fps == 10
            assert app.state.visualizer_fps == 10
            app.exit()

    _run(run_app())
    persisted = load_state(paths.state_path())
    assert persisted.visualizer_fps == 10


def test_cli_visualizer_fps_override_is_clamped(tmp_path, monkeypatch) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    app = TzPlayerApp(auto_init=False, backend_name="fake", visualizer_fps_override=99)

    async def run_app() -> None:
        async with app.run_test():
            await asyncio.sleep(0)
            await app._initialize_state()
            assert app.visualizer_host is not None
            assert app.visualizer_host.target_fps == 30
            assert app.state.visualizer_fps == 30
            app.exit()

    _run(run_app())


def test_cli_visualizer_plugin_paths_override_persisted_state(
    tmp_path, monkeypatch
) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    save_state(
        paths.state_path(),
        AppState(
            playback_backend="fake",
            visualizer_plugin_paths=("persisted.plugins",),
        ),
    )
    captured_paths: list[str] = []

    def fake_built_in(
        cls,
        *,
        local_plugin_paths=None,
        plugin_security_mode="warn",
        plugin_runtime_mode="in-process",
    ):
        if local_plugin_paths:
            captured_paths.extend(local_plugin_paths)
        return VisualizerRegistry({"viz.default": VizDefault}, default_id="viz.default")

    monkeypatch.setattr(
        app_module.VisualizerRegistry,
        "built_in",
        classmethod(fake_built_in),
    )
    app = TzPlayerApp(
        auto_init=False,
        backend_name="fake",
        visualizer_plugin_paths_override=["cli.plugins"],
    )

    async def run_app() -> None:
        async with app.run_test():
            await asyncio.sleep(0)
            await app._initialize_state()
            assert app.state.visualizer_plugin_paths == ("cli.plugins",)
            app.exit()

    _run(run_app())
    persisted = load_state(paths.state_path())
    assert persisted.visualizer_plugin_paths == ("cli.plugins",)
    assert "cli.plugins" in captured_paths
    assert any(
        Path(path).parts[-2:] == ("visualizers", "plugins") for path in captured_paths
    )


def test_app_spectrum_request_capability_follows_active_visualizer(
    tmp_path, monkeypatch
) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    registry = VisualizerRegistry(
        {"viz.default": VizDefault, "viz.spectrum": VizSpectrum},
        default_id="viz.default",
    )
    _stub_registry_built_in(monkeypatch, registry)
    app = TzPlayerApp(auto_init=False, backend_name="fake")

    async def run_app() -> None:
        async with app.run_test() as pilot:
            await asyncio.sleep(0)
            await app._initialize_state()
            assert app.visualizer_host is not None
            assert app.visualizer_host.active_id == "viz.default"
            assert app._active_visualizer_requests_spectrum() is False

            await pilot.press("z")
            await asyncio.sleep(0)
            assert app.visualizer_host.active_id == "viz.spectrum"
            assert app._active_visualizer_requests_spectrum() is True
            app.exit()

    _run(run_app())
