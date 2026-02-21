"""Regression tests for non-blocking IO path contracts."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

import tz_player.services.metadata_service as metadata_service_module
import tz_player.ui.playlist_pane as playlist_pane_module
from tz_player.ui.playlist_pane import PlaylistPane
from tz_player.utils.async_utils import run_blocking, run_cpu_blocking


def _run(coro):
    """Run async helper from sync test code."""
    return asyncio.run(coro)


def test_metadata_safe_stat_uses_run_blocking(monkeypatch, tmp_path) -> None:
    calls: list[tuple[object, tuple[object, ...]]] = []

    class FakeStat:
        st_mtime_ns = 123
        st_size = 456

    async def fake_run_blocking(func, /, *args, **kwargs):
        calls.append((func, args))
        return FakeStat()

    monkeypatch.setattr(metadata_service_module, "run_blocking", fake_run_blocking)

    path = tmp_path / "track.mp3"
    stat = _run(metadata_service_module._safe_stat(path))

    assert stat is not None
    assert stat.mtime_ns == 123
    assert stat.size_bytes == 456
    assert len(calls) == 1
    func, args = calls[0]
    assert getattr(func, "__name__", "") == "stat"
    assert args == ()


def test_run_blocking_rejects_non_callable() -> None:
    with pytest.raises(TypeError, match="func must be callable"):
        _run(run_blocking(None))  # type: ignore[arg-type]


def test_run_cpu_blocking_rejects_non_callable() -> None:
    with pytest.raises(TypeError, match="func must be callable"):
        _run(run_cpu_blocking(None))  # type: ignore[arg-type]


def test_add_folder_scans_via_run_blocking(monkeypatch, tmp_path) -> None:
    pane = PlaylistPane()

    class FakeStore:
        async def add_tracks(self, playlist_id: int, paths: list[Path]) -> int:
            del playlist_id, paths
            return 0

    pane.store = FakeStore()  # type: ignore[assignment]
    folder = tmp_path / "music"
    folder.mkdir(parents=True, exist_ok=True)
    track = folder / "song.mp3"
    track.write_bytes(b"")

    calls: list[tuple[object, tuple[object, ...]]] = []
    added: dict[str, object] = {}

    async def fake_run_blocking(func, /, *args, **kwargs):
        calls.append((func, args))
        return func(*args, **kwargs)

    async def fake_prompt_folder() -> Path:
        return folder

    async def fake_run_store_action(label: str, func, *args) -> None:  # type: ignore[no-untyped-def]
        added["label"] = label
        added["func"] = func
        added["args"] = args

    monkeypatch.setattr(playlist_pane_module, "run_blocking", fake_run_blocking)
    pane._prompt_folder = fake_prompt_folder  # type: ignore[assignment]
    pane._run_store_action = fake_run_store_action  # type: ignore[assignment]

    _run(pane._add_folder())

    assert len(calls) == 1
    func, args = calls[0]
    assert func is playlist_pane_module._scan_media_files
    assert args == (Path(folder),)
    assert added["label"] == "add folder"
    paths = added["args"][0]
    assert paths == [track]


def test_advanced_visualizer_modules_avoid_blocking_imports() -> None:
    """Guard against obvious blocking/runtime-risk imports in render modules."""
    root = Path(__file__).resolve().parents[1]
    visualizer_modules = [
        root / "src/tz_player/visualizers/waterfall.py",
        root / "src/tz_player/visualizers/terrain.py",
        root / "src/tz_player/visualizers/reactor.py",
        root / "src/tz_player/visualizers/radial.py",
        root / "src/tz_player/visualizers/typography.py",
    ]
    forbidden_roots = {
        "subprocess",
        "socket",
        "http",
        "urllib",
        "requests",
        "sqlite3",
    }
    for module in visualizer_modules:
        parsed = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(parsed):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_name = alias.name.split(".")[0]
                    assert root_name not in forbidden_roots, (
                        f"{module.name} imports forbidden module '{alias.name}'"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module is None:
                    continue
                root_name = node.module.split(".")[0]
                assert root_name not in forbidden_roots, (
                    f"{module.name} imports forbidden module '{node.module}'"
                )


def test_app_visualizer_registry_build_uses_run_blocking() -> None:
    root = Path(__file__).resolve().parents[1]
    module = root / "src/tz_player/app.py"
    parsed = ast.parse(module.read_text(encoding="utf-8"))
    method = _find_method(
        parsed, class_name="TzPlayerApp", method_name="_start_visualizer"
    )

    found = False
    for node in ast.walk(method):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "run_blocking":
            continue
        if not node.args:
            continue
        first = node.args[0]
        if not isinstance(first, ast.Attribute):
            continue
        if not isinstance(first.value, ast.Name):
            continue
        if first.value.id == "VisualizerRegistry" and first.attr == "built_in":
            found = True
            break

    assert found, (
        "Expected _start_visualizer to call run_blocking(VisualizerRegistry.built_in, ...)"
    )


def test_app_visualizer_timer_uses_render_request_callback() -> None:
    root = Path(__file__).resolve().parents[1]
    module = root / "src/tz_player/app.py"
    parsed = ast.parse(module.read_text(encoding="utf-8"))
    method = _find_method(
        parsed, class_name="TzPlayerApp", method_name="_start_visualizer"
    )

    found = False
    for node in ast.walk(method):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "set_interval":
            continue
        if len(node.args) < 2:
            continue
        callback = node.args[1]
        if (
            isinstance(callback, ast.Attribute)
            and isinstance(callback.value, ast.Name)
            and callback.value.id == "self"
            and callback.attr == "_request_visualizer_render"
        ):
            found = True
            break

    assert found, (
        "Expected visualizer timer callback to be self._request_visualizer_render"
    )


def test_app_visualizer_render_uses_run_cpu_blocking() -> None:
    root = Path(__file__).resolve().parents[1]
    module = root / "src/tz_player/app.py"
    parsed = ast.parse(module.read_text(encoding="utf-8"))
    method = _find_method(
        parsed,
        class_name="TzPlayerApp",
        method_name="_render_visualizer_frame_async",
    )

    found = False
    for node in ast.walk(method):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "run_cpu_blocking"
        ):
            found = True
            break

    assert found, (
        "Expected _render_visualizer_frame_async to offload render via run_cpu_blocking"
    )


def _find_method(
    module: ast.Module, *, class_name: str, method_name: str
) -> ast.AsyncFunctionDef | ast.FunctionDef:
    for node in module.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for child in node.body:
            if (
                isinstance(child, (ast.AsyncFunctionDef, ast.FunctionDef))
                and child.name == method_name
            ):
                return child
    raise AssertionError(f"Method {class_name}.{method_name} not found")
