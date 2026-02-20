"""Opt-in performance checks (excluded from default CI)."""

from __future__ import annotations

import asyncio
import os
import sqlite3
import statistics
import time
from pathlib import Path

import pytest

import tz_player.paths as paths
from tz_player.app import TzPlayerApp
from tz_player.services.playlist_store import POS_STEP, PlaylistStore

pytestmark = pytest.mark.skipif(
    os.getenv("TZ_PLAYER_RUN_PERF") != "1",
    reason="Set TZ_PLAYER_RUN_PERF=1 to run opt-in performance checks.",
)

STARTUP_BUDGET_S = 2.0
INTERACTION_BUDGET_S = 0.1
LARGE_PLAYLIST_SIZE = 100_000
LARGE_WINDOW_BUDGET_S = 0.20
LARGE_LIST_IDS_BUDGET_S = 0.65
LARGE_SEARCH_BUDGET_S = 2.50
LARGE_SEARCH_BROAD_BUDGET_S = 2.80
LARGE_SEARCH_MULTI_TOKEN_BUDGET_S = 12.00
LARGE_SEARCH_MISS_BUDGET_S = 3.00
LARGE_RANDOM_MEDIAN_BUDGET_S = 0.012


class FakeAppDirs:
    """Path-dir stub routing app dirs into temp directories for perf tests."""

    def __init__(self, data_dir: Path, config_dir: Path) -> None:
        self.user_data_dir = str(data_dir)
        self.user_config_dir = str(config_dir)


def _run(coro):
    """Run async performance scenario from sync test body."""
    return asyncio.run(coro)


def _setup_dirs(tmp_path, monkeypatch) -> None:
    """Patch AppDirs to avoid touching real user data/config locations."""
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"

    def fake_app_dirs(app_name: str, appauthor: bool | None = None) -> FakeAppDirs:
        return FakeAppDirs(data_dir, config_dir)

    monkeypatch.setattr(paths, "AppDirs", fake_app_dirs)
    paths.get_app_dirs.cache_clear()


def _seed_large_playlist(db_path: Path, playlist_id: int, total: int) -> None:
    """Insert a large synthetic playlist directly for scale-oriented perf checks."""
    batch_tracks: list[tuple[int, str, str]] = []
    batch_items: list[tuple[int, int, int]] = []
    with sqlite3.connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        for index in range(total):
            tag = "needle_" if index % 200 == 0 else ""
            path = f"/perf/{tag}track_{index:06d}.mp3"
            track_id = index + 1
            batch_tracks.append((track_id, path, path))
            batch_items.append((playlist_id, track_id, (index + 1) * POS_STEP))
            if len(batch_tracks) >= 5000:
                conn.executemany(
                    "INSERT INTO tracks (id, path, path_norm) VALUES (?, ?, ?)",
                    batch_tracks,
                )
                conn.executemany(
                    """
                    INSERT INTO playlist_items (playlist_id, track_id, pos_key)
                    VALUES (?, ?, ?)
                    """,
                    batch_items,
                )
                batch_tracks.clear()
                batch_items.clear()
        if batch_tracks:
            conn.executemany(
                "INSERT INTO tracks (id, path, path_norm) VALUES (?, ?, ?)",
                batch_tracks,
            )
            conn.executemany(
                """
                INSERT INTO playlist_items (playlist_id, track_id, pos_key)
                VALUES (?, ?, ?)
                """,
                batch_items,
            )


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


def test_large_playlist_store_navigation_search_and_random_budget(tmp_path) -> None:
    db_path = tmp_path / "library.sqlite"
    store = PlaylistStore(db_path)
    _run(store.initialize())
    playlist_id = _run(store.create_playlist("PerfLarge"))
    _seed_large_playlist(db_path, playlist_id, LARGE_PLAYLIST_SIZE)

    start = time.perf_counter()
    rows = _run(store.fetch_window(playlist_id, LARGE_PLAYLIST_SIZE - 100, 100))
    window_elapsed = time.perf_counter() - start
    assert len(rows) == 100
    assert window_elapsed <= LARGE_WINDOW_BUDGET_S, (
        f"Window fetch elapsed {window_elapsed:.3f}s exceeded budget "
        f"{LARGE_WINDOW_BUDGET_S:.3f}s"
    )

    start = time.perf_counter()
    item_ids = _run(store.list_item_ids(playlist_id))
    list_elapsed = time.perf_counter() - start
    assert len(item_ids) == LARGE_PLAYLIST_SIZE
    assert list_elapsed <= LARGE_LIST_IDS_BUDGET_S, (
        f"list_item_ids elapsed {list_elapsed:.3f}s exceeded budget "
        f"{LARGE_LIST_IDS_BUDGET_S:.3f}s"
    )

    start = time.perf_counter()
    search_ids = _run(store.search_item_ids(playlist_id, "needle", limit=1000))
    search_elapsed = time.perf_counter() - start
    assert len(search_ids) == LARGE_PLAYLIST_SIZE // 200
    assert search_elapsed <= LARGE_SEARCH_BUDGET_S, (
        f"search_item_ids elapsed {search_elapsed:.3f}s exceeded budget "
        f"{LARGE_SEARCH_BUDGET_S:.3f}s"
    )

    start = time.perf_counter()
    broad_ids = _run(store.search_item_ids(playlist_id, "track", limit=1000))
    broad_elapsed = time.perf_counter() - start
    assert len(broad_ids) == 1000
    assert broad_elapsed <= LARGE_SEARCH_BROAD_BUDGET_S, (
        f"Broad search elapsed {broad_elapsed:.3f}s exceeded budget "
        f"{LARGE_SEARCH_BROAD_BUDGET_S:.3f}s"
    )

    start = time.perf_counter()
    multi_ids = _run(store.search_item_ids(playlist_id, "needle 000", limit=1000))
    multi_elapsed = time.perf_counter() - start
    assert len(multi_ids) > 0
    assert multi_elapsed <= LARGE_SEARCH_MULTI_TOKEN_BUDGET_S, (
        f"Multi-token search elapsed {multi_elapsed:.3f}s exceeded budget "
        f"{LARGE_SEARCH_MULTI_TOKEN_BUDGET_S:.3f}s"
    )

    start = time.perf_counter()
    miss_ids = _run(store.search_item_ids(playlist_id, "zzzxxyyynotfound", limit=1000))
    miss_elapsed = time.perf_counter() - start
    assert miss_ids == []
    assert miss_elapsed <= LARGE_SEARCH_MISS_BUDGET_S, (
        f"Miss search elapsed {miss_elapsed:.3f}s exceeded budget "
        f"{LARGE_SEARCH_MISS_BUDGET_S:.3f}s"
    )

    async def sample_random_latencies() -> float:
        samples: list[float] = []
        for _ in range(40):
            begin = time.perf_counter()
            selected = await store.get_random_item_id(playlist_id)
            samples.append(time.perf_counter() - begin)
            assert selected is not None
        return statistics.median(samples)

    median_random = _run(sample_random_latencies())
    assert median_random <= LARGE_RANDOM_MEDIAN_BUDGET_S, (
        f"Median get_random_item_id elapsed {median_random:.4f}s exceeded budget "
        f"{LARGE_RANDOM_MEDIAN_BUDGET_S:.4f}s"
    )
