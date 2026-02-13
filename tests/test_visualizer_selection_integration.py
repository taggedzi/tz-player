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
    def __init__(self, data_dir: Path, config_dir: Path) -> None:
        self.user_data_dir = str(data_dir)
        self.user_config_dir = str(config_dir)


def _run(coro):
    return asyncio.run(coro)


def _setup_dirs(tmp_path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"

    def fake_app_dirs(app_name: str, appauthor: bool | None = None) -> FakeAppDirs:
        return FakeAppDirs(data_dir, config_dir)

    monkeypatch.setattr(paths, "AppDirs", fake_app_dirs)
    paths.get_app_dirs.cache_clear()


@dataclass
class VizOne:
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
    plugin_id: str = "viz.default"
    display_name: str = "Viz Default"

    def on_activate(self, context: VisualizerContext) -> None:
        return None

    def on_deactivate(self) -> None:
        return None

    def render(self, frame: VisualizerFrameInput) -> str:
        return "default"


def test_visualizer_selection_persists_across_restart(tmp_path, monkeypatch) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    registry = VisualizerRegistry(
        {"viz.one": VizOne, "viz.two": VizTwo},
        default_id="viz.one",
    )
    monkeypatch.setattr(
        app_module.VisualizerRegistry,
        "built_in",
        classmethod(lambda cls: registry),
    )

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
    monkeypatch.setattr(
        app_module.VisualizerRegistry,
        "built_in",
        classmethod(lambda cls: registry),
    )

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
