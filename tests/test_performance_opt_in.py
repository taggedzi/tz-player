"""Opt-in performance checks (excluded from default CI)."""

from __future__ import annotations

import asyncio
import os
import statistics
import time
from pathlib import Path

import pytest

import tz_player.paths as paths
from tz_player.app import TzPlayerApp

pytestmark = pytest.mark.skipif(
    os.getenv("TZ_PLAYER_RUN_PERF") != "1",
    reason="Set TZ_PLAYER_RUN_PERF=1 to run opt-in performance checks.",
)

STARTUP_BUDGET_S = 2.0
INTERACTION_BUDGET_S = 0.1


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


def test_startup_to_interactive_focus_budget(tmp_path, monkeypatch) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    app = TzPlayerApp(auto_init=False, backend_name="fake")

    async def run_app() -> float:
        async with app.run_test():
            await asyncio.sleep(0)
            start = time.perf_counter()
            await app._initialize_state()
            elapsed = time.perf_counter() - start
            app.exit()
            return elapsed

    elapsed = _run(run_app())
    assert elapsed <= STARTUP_BUDGET_S, (
        f"Startup elapsed {elapsed:.3f}s exceeded budget {STARTUP_BUDGET_S:.3f}s"
    )


def test_core_interaction_latency_budget(tmp_path, monkeypatch) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    app = TzPlayerApp(auto_init=False, backend_name="fake")

    async def run_app() -> float:
        async with app.run_test():
            await asyncio.sleep(0)
            await app._initialize_state()
            samples: list[float] = []
            for _ in range(5):
                start = time.perf_counter()
                await app.action_volume_up()
                samples.append(time.perf_counter() - start)
            app.exit()
            return statistics.median(samples)

    median_elapsed = _run(run_app())
    assert median_elapsed <= INTERACTION_BUDGET_S, (
        "Median interaction latency "
        f"{median_elapsed * 1000:.1f}ms exceeded {INTERACTION_BUDGET_S * 1000:.1f}ms budget"
    )
