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
from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.host import VisualizerHost
from tz_player.visualizers.registry import VisualizerRegistry

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
ADVANCED_VIZ_RENDER_MEDIAN_BUDGET_S = 0.035
ADVANCED_VIZ_RENDER_MAX_BUDGET_S = 0.120
ADVANCED_VIZ_FRAME_COUNT = 120
ADVANCED_VIZ_PANE_WIDTH = 160
ADVANCED_VIZ_PANE_HEIGHT = 50
PROFILE_MATRIX_FRAME_COUNT = 80
PROFILE_INTERACTION_BUDGET_S = 0.12
PROFILE_RENDER_BUDGETS = {
    "safe": {"fps": 10, "median_s": 0.050, "max_s": 0.180, "max_throttle_rate": 0.01},
    "balanced": {
        "fps": 16,
        "median_s": 0.045,
        "max_s": 0.160,
        "max_throttle_rate": 0.03,
    },
    "aggressive": {
        "fps": 22,
        "median_s": 0.040,
        "max_s": 0.140,
        "max_throttle_rate": 0.06,
    },
}
ADVANCED_VIZ_IDS = (
    "viz.spectrogram.waterfall",
    "viz.spectrum.terrain",
    "viz.reactor.particles",
    "viz.particle.gravity_well",
    "viz.particle.shockwave_rings",
    "viz.particle.rain_reactive",
    "viz.particle.orbital_system",
    "viz.particle.ember_field",
    "viz.particle.magnetic_grid",
    "viz.particle.audio_tornado",
    "viz.particle.constellation",
    "viz.spectrum.radial",
    "viz.typography.glitch",
    "viz.waveform.proxy",
    "viz.waveform.neon",
)


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


@pytest.mark.parametrize("profile", ("safe", "balanced", "aggressive"))
def test_profile_interaction_latency_budget_matrix(
    tmp_path, monkeypatch, profile: str
) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    app = TzPlayerApp(
        auto_init=False,
        backend_name="fake",
        visualizer_responsiveness_profile_override=profile,
    )

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
    assert median_elapsed <= PROFILE_INTERACTION_BUDGET_S, (
        f"{profile} median interaction latency {median_elapsed * 1000:.1f}ms exceeded "
        f"{PROFILE_INTERACTION_BUDGET_S * 1000:.1f}ms budget"
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


def test_advanced_visualizer_large_pane_render_budget() -> None:
    registry = VisualizerRegistry.built_in()
    spectrum = bytes(((idx * 9) % 256) for idx in range(48))
    context = VisualizerContext(ansi_enabled=False, unicode_enabled=True)

    for profile, budget in PROFILE_RENDER_BUDGETS.items():
        for plugin_id in ADVANCED_VIZ_IDS:
            host = VisualizerHost(registry, target_fps=int(budget["fps"]))
            host.activate(plugin_id, context)
            samples: list[float] = []
            throttled = 0
            for frame_idx in range(PROFILE_MATRIX_FRAME_COUNT):
                frame = VisualizerFrameInput(
                    frame_index=frame_idx,
                    monotonic_s=frame_idx / 60.0,
                    width=ADVANCED_VIZ_PANE_WIDTH,
                    height=ADVANCED_VIZ_PANE_HEIGHT,
                    status="playing",
                    position_s=frame_idx * 0.04,
                    duration_s=300.0,
                    volume=72.0,
                    speed=1.0,
                    repeat_mode="OFF",
                    shuffle=False,
                    track_id=1,
                    track_path="/perf/advanced.mp3",
                    title="Perf Signal",
                    artist="Bench",
                    album="Suite",
                    level_left=0.65,
                    level_right=0.58,
                    spectrum_bands=spectrum,
                    spectrum_source="cache",
                    spectrum_status="ready",
                    beat_is_onset=(frame_idx % 24 == 0),
                    beat_strength=0.8 if frame_idx % 24 == 0 else 0.2,
                    beat_bpm=126.0,
                    beat_source="cache",
                    beat_status="ready",
                )
                begin = time.perf_counter()
                output = host.render_frame(frame, context)
                elapsed = time.perf_counter() - begin
                if output == "Visualizer throttled":
                    throttled += 1
                    continue
                samples.append(elapsed)
                assert output
            host.shutdown()

            assert samples
            median_elapsed = statistics.median(samples)
            worst_elapsed = max(samples)
            throttle_rate = throttled / PROFILE_MATRIX_FRAME_COUNT

            assert median_elapsed <= float(budget["median_s"]), (
                f"{profile}/{plugin_id} median render {median_elapsed:.4f}s exceeded "
                f"budget {float(budget['median_s']):.4f}s"
            )
            assert worst_elapsed <= float(budget["max_s"]), (
                f"{profile}/{plugin_id} max render {worst_elapsed:.4f}s exceeded "
                f"budget {float(budget['max_s']):.4f}s"
            )
            assert throttle_rate <= float(budget["max_throttle_rate"]), (
                f"{profile}/{plugin_id} throttle rate {throttle_rate:.3f} exceeded "
                f"budget {float(budget['max_throttle_rate']):.3f}"
            )
