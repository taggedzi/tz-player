"""Opt-in performance checks (excluded from default CI)."""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import statistics
import time
import uuid
from contextlib import suppress
from pathlib import Path

import pytest

import tz_player.paths as paths
import tz_player.services.playlist_store as playlist_store_module
from tz_player.app import TzPlayerApp
from tz_player.perf_benchmarking import (
    PerfRunResult,
    PerfScenarioResult,
    build_perf_media_manifest,
    perf_media_skip_reason,
    resolve_perf_media_dir,
    summarize_samples,
    utc_now_iso,
    write_perf_run_artifact,
)
from tz_player.perf_observability import (
    capture_perf_events,
    capture_process_resource_snapshot,
    count_events_by_name,
    diff_process_resource_snapshots,
    event_latency_ms_since,
    probe_method_calls,
    wait_for_captured_event,
)
from tz_player.services.audio_analysis_bundle import analyze_track_analysis_bundle
from tz_player.services.audio_envelope_analysis import (
    analyze_track_envelope,
    ffmpeg_available,
    requires_ffmpeg_for_envelope,
)
from tz_player.services.audio_envelope_store import SqliteEnvelopeStore
from tz_player.services.audio_level_service import AudioLevelService
from tz_player.services.beat_service import BeatService
from tz_player.services.beat_store import BeatParams, SqliteBeatStore
from tz_player.services.fake_backend import FakePlaybackBackend
from tz_player.services.player_service import PlayerService, TrackInfo
from tz_player.services.playlist_store import POS_STEP, PlaylistStore
from tz_player.services.spectrum_service import SpectrumService
from tz_player.services.spectrum_store import SpectrumParams, SqliteSpectrumStore
from tz_player.services.waveform_proxy_service import WaveformProxyService
from tz_player.services.waveform_proxy_store import (
    SqliteWaveformProxyStore,
    WaveformProxyParams,
)
from tz_player.utils.async_utils import run_cpu_bound
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
VISUALIZER_BENCH_ARTIFACT_FRAME_COUNT = 40
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
    "viz.particle.data_core_frag",
    "viz.particle.plasma_stream",
    "viz.spectrum.radial",
    "viz.typography.glitch",
    "viz.waveform.proxy",
    "viz.waveform.neon",
)

VISUALIZER_TIER_MAP = {
    "viz.spectrum.radial": "cheap",
    "viz.waveform.proxy": "cheap",
    "viz.waveform.neon": "cheap",
    "viz.typography.glitch": "medium",
    "viz.spectrogram.waterfall": "medium",
    "viz.spectrum.terrain": "medium",
    "viz.reactor.particles": "medium",
    "viz.particle.constellation": "medium",
    "viz.particle.rain_reactive": "medium",
    "viz.particle.ember_field": "medium",
    "viz.particle.gravity_well": "heavy",
    "viz.particle.shockwave_rings": "heavy",
    "viz.particle.orbital_system": "heavy",
    "viz.particle.magnetic_grid": "heavy",
    "viz.particle.audio_tornado": "heavy",
    "viz.particle.data_core_frag": "heavy",
    "viz.particle.plasma_stream": "heavy",
}


class FakeAppDirs:
    """Path-dir stub routing app dirs into temp directories for perf tests."""

    def __init__(self, data_dir: Path, config_dir: Path) -> None:
        self.user_data_dir = str(data_dir)
        self.user_config_dir = str(config_dir)


def _run(coro):
    """Run async performance scenario from sync test body."""
    return asyncio.run(coro)


def _cpu_spin(iterations: int) -> int:
    total = 0
    for idx in range(iterations):
        total += (idx * idx) % 97
    return total


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


def test_large_playlist_db_query_matrix_benchmark_artifact(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "library.sqlite"
    store = PlaylistStore(db_path)
    _run(store.initialize())
    playlist_id = _run(store.create_playlist("PerfLargeArtifact"))
    _seed_large_playlist(db_path, playlist_id, LARGE_PLAYLIST_SIZE)

    monkeypatch.setattr(playlist_store_module, "_PERF_WARN_MS", 0.0)
    root = logging.getLogger()
    prior_level = root.level
    root.setLevel(logging.INFO)

    async def sample_random_latencies() -> list[float]:
        samples: list[float] = []
        for _ in range(20):
            begin = time.perf_counter()
            selected = await store.get_random_item_id(playlist_id)
            samples.append((time.perf_counter() - begin) * 1000.0)
            assert selected is not None
        return samples

    try:
        with capture_perf_events(
            logger=root,
            event_names={"playlist_store_slow_query"},
        ) as capture:
            timings_ms: dict[str, list[float]] = {}

            start = time.perf_counter()
            rows = _run(store.fetch_window(playlist_id, LARGE_PLAYLIST_SIZE - 100, 100))
            timings_ms["fetch_window_tail_ms"] = [
                (time.perf_counter() - start) * 1000.0
            ]
            assert len(rows) == 100

            start = time.perf_counter()
            top_rows = _run(store.fetch_window(playlist_id, 0, 100))
            timings_ms["fetch_window_head_ms"] = [
                (time.perf_counter() - start) * 1000.0
            ]
            assert len(top_rows) == 100

            start = time.perf_counter()
            item_ids = _run(store.list_item_ids(playlist_id))
            timings_ms["list_item_ids_ms"] = [(time.perf_counter() - start) * 1000.0]
            assert len(item_ids) == LARGE_PLAYLIST_SIZE

            start = time.perf_counter()
            needle_ids = _run(store.search_item_ids(playlist_id, "needle", limit=1000))
            timings_ms["search_needle_ms"] = [(time.perf_counter() - start) * 1000.0]
            assert len(needle_ids) == LARGE_PLAYLIST_SIZE // 200

            start = time.perf_counter()
            broad_ids = _run(store.search_item_ids(playlist_id, "track", limit=1000))
            timings_ms["search_broad_ms"] = [(time.perf_counter() - start) * 1000.0]
            assert len(broad_ids) == 1000

            start = time.perf_counter()
            multi_ids = _run(
                store.search_item_ids(playlist_id, "needle 000", limit=1000)
            )
            timings_ms["search_multi_token_ms"] = [
                (time.perf_counter() - start) * 1000.0
            ]
            assert multi_ids

            start = time.perf_counter()
            miss_ids = _run(
                store.search_item_ids(playlist_id, "zzzxxyyynotfound", limit=1000)
            )
            timings_ms["search_miss_ms"] = [(time.perf_counter() - start) * 1000.0]
            assert miss_ids == []

            timings_ms["random_item_ms"] = _run(sample_random_latencies())

            slow_events = capture.snapshot()
    finally:
        root.setLevel(prior_level)

    event_counts = count_events_by_name(slow_events)
    slow_ops: dict[str, int] = {}
    slow_modes: dict[str, int] = {}
    for event in slow_events:
        op = event.context.get("operation")
        if isinstance(op, str):
            slow_ops[op] = slow_ops.get(op, 0) + 1
        mode = event.context.get("mode")
        if isinstance(mode, str):
            slow_modes[mode] = slow_modes.get(mode, 0) + 1

    metrics = {
        metric_name: summarize_samples(samples, unit="ms")
        for metric_name, samples in timings_ms.items()
    }
    run = PerfRunResult(
        run_id=f"db-query-matrix-{uuid.uuid4().hex[:8]}",
        created_at=utc_now_iso(),
        app_version=None,
        git_sha=None,
        machine={"runner": "pytest-opt-in"},
        config={
            "scenario": "large_playlist_db_query_matrix",
            "playlist_size": LARGE_PLAYLIST_SIZE,
            "perf_warn_ms_override": 0.0,
        },
        scenarios=[
            PerfScenarioResult(
                scenario_id="large_playlist_db_query_matrix",
                category="database",
                status="pass",
                elapsed_s=round(
                    sum(sum(samples) for samples in timings_ms.values()) / 1000.0,
                    6,
                ),
                metrics=metrics,
                counters={
                    "playlist_size": LARGE_PLAYLIST_SIZE,
                    "slow_event_count": len(slow_events),
                    "playlist_store_slow_query_events": event_counts.get(
                        "playlist_store_slow_query", 0
                    ),
                    "slow_ops_distinct": len(slow_ops),
                    "slow_modes_distinct": len(slow_modes),
                },
                metadata={
                    "slow_operation_counts": slow_ops,
                    "slow_mode_counts": slow_modes,
                    "captured_event_names": event_counts,
                },
            )
        ],
    )
    artifact_path = write_perf_run_artifact(run, results_dir=tmp_path / "perf_results")
    assert artifact_path.exists()
    assert event_counts.get("playlist_store_slow_query", 0) >= 1


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


def test_advanced_visualizer_matrix_benchmark_artifact(tmp_path) -> None:
    registry = VisualizerRegistry.built_in()
    spectrum = bytes(((idx * 9) % 256) for idx in range(48))
    context = VisualizerContext(ansi_enabled=False, unicode_enabled=True)
    scenarios: list[PerfScenarioResult] = []

    for profile, budget in PROFILE_RENDER_BUDGETS.items():
        profile_metrics = {}
        counters: dict[str, int | float] = {
            "frame_count": VISUALIZER_BENCH_ARTIFACT_FRAME_COUNT
        }
        tier_counts = {"cheap": 0, "medium": 0, "heavy": 0}
        for plugin_id in ADVANCED_VIZ_IDS:
            host = VisualizerHost(registry, target_fps=int(budget["fps"]))
            host.activate(plugin_id, context)
            samples_ms: list[float] = []
            throttled = 0
            for frame_idx in range(VISUALIZER_BENCH_ARTIFACT_FRAME_COUNT):
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
                elapsed_ms = (time.perf_counter() - begin) * 1000.0
                if output == "Visualizer throttled":
                    throttled += 1
                    continue
                samples_ms.append(elapsed_ms)
                assert output
            host.shutdown()

            assert samples_ms
            plugin_key = plugin_id.replace(".", "_")
            profile_metrics[f"{plugin_key}_render_ms"] = summarize_samples(
                samples_ms, unit="ms"
            )
            counters[f"{plugin_key}_throttled_frames"] = throttled
            counters[f"{plugin_key}_throttle_rate"] = round(
                throttled / VISUALIZER_BENCH_ARTIFACT_FRAME_COUNT, 4
            )
            tier = VISUALIZER_TIER_MAP.get(plugin_id, "unknown")
            counters[f"{plugin_key}_tier"] = tier
            if tier in tier_counts:
                tier_counts[tier] += 1

        scenarios.append(
            PerfScenarioResult(
                scenario_id=f"visualizer_matrix_render_{profile}",
                category="visualizer",
                status="pass",
                elapsed_s=round(
                    sum(
                        metric.mean_value * metric.count
                        for metric in profile_metrics.values()
                    )
                    / 1000.0,
                    6,
                ),
                metrics=profile_metrics,
                counters={
                    **counters,
                    **{f"tier_count_{k}": v for k, v in tier_counts.items()},
                },
                metadata={
                    "profile": profile,
                    "target_fps": int(budget["fps"]),
                    "plugin_ids": list(ADVANCED_VIZ_IDS),
                    "plugin_tiers": {
                        plugin_id: VISUALIZER_TIER_MAP.get(plugin_id, "unknown")
                        for plugin_id in ADVANCED_VIZ_IDS
                    },
                },
            )
        )

    run = PerfRunResult(
        run_id=f"visualizer-matrix-{uuid.uuid4().hex[:8]}",
        created_at=utc_now_iso(),
        app_version=None,
        git_sha=None,
        machine={"runner": "pytest-opt-in"},
        config={
            "scenario": "advanced_visualizer_matrix_benchmark_artifact",
            "frame_count": VISUALIZER_BENCH_ARTIFACT_FRAME_COUNT,
            "pane_width": ADVANCED_VIZ_PANE_WIDTH,
            "pane_height": ADVANCED_VIZ_PANE_HEIGHT,
        },
        scenarios=scenarios,
    )
    artifact_path = write_perf_run_artifact(run, results_dir=tmp_path / "perf_results")
    assert artifact_path.exists()
    assert len(scenarios) == len(PROFILE_RENDER_BUDGETS)


def test_local_perf_media_corpus_manifest_smoke() -> None:
    media_dir = resolve_perf_media_dir()
    skip_reason = perf_media_skip_reason(media_dir)
    if skip_reason is not None:
        pytest.skip(skip_reason)
    assert media_dir is not None

    manifest = build_perf_media_manifest(media_dir, probe_durations=False)
    assert int(manifest["track_count"]) > 0
    assert int(manifest["total_bytes"]) > 0
    assert isinstance(manifest["formats"], dict)


class _DelayedFramePreloadStub:
    def __init__(self, *, frame_count: int, delay_s: float) -> None:
        self.frame_count = frame_count
        self.delay_s = delay_s
        self.preload_calls: list[str] = []
        self.clear_calls: list[str] = []

    async def preload_track(self, track_path: str, **_kwargs) -> int:
        self.preload_calls.append(track_path)
        await asyncio.sleep(self.delay_s)
        return self.frame_count

    def clear_track_cache(self, track_path: str | None = None) -> None:
        if track_path is not None:
            self.clear_calls.append(track_path)


class _DelayedEnvelopeProvider:
    def __init__(self, *, frame_count: int, delay_s: float) -> None:
        self.frame_count = frame_count
        self.delay_s = delay_s
        self.calls: list[str] = []

    async def get_level_at(self, track_path: str, position_ms: int):
        _ = (track_path, position_ms)
        return None

    async def list_levels(self, track_path: str) -> list[tuple[int, float, float]]:
        self.calls.append(track_path)
        await asyncio.sleep(self.delay_s)
        return [(idx * 20, 0.2, 0.25) for idx in range(self.frame_count)]

    async def touch_envelope_access(self, track_path: str) -> None:
        _ = track_path


def test_player_service_track_switch_and_preload_benchmark_smoke(tmp_path) -> None:
    media_dir = resolve_perf_media_dir()
    skip_reason = perf_media_skip_reason(media_dir)
    if skip_reason is not None:
        pytest.skip(skip_reason)
    assert media_dir is not None

    corpus_files = sorted(
        path
        for path in media_dir.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".mp3", ".flac", ".wav", ".ogg", ".m4a"}
    )
    if len(corpus_files) < 3:
        pytest.skip("Need at least 3 audio files in perf corpus for switch benchmark.")
    sample_files = corpus_files[:5]

    async def emit_event(_event: object) -> None:
        return None

    async def track_info_provider(_playlist_id: int, item_id: int) -> TrackInfo | None:
        if item_id < 1 or item_id > len(sample_files):
            return None
        path = sample_files[item_id - 1]
        return TrackInfo(
            title=path.stem,
            artist="Perf",
            album="Perf",
            year=None,
            path=str(path),
            duration_ms=180_000,
        )

    async def run_scenario() -> tuple[list[float], list[float], Path]:
        spectrum_stub = _DelayedFramePreloadStub(frame_count=4096, delay_s=0.008)
        beat_stub = _DelayedFramePreloadStub(frame_count=4096, delay_s=0.006)
        wave_stub = _DelayedFramePreloadStub(frame_count=6144, delay_s=0.010)
        envelope_provider = _DelayedEnvelopeProvider(frame_count=3000, delay_s=0.005)
        service = PlayerService(
            emit_event=emit_event,
            track_info_provider=track_info_provider,
            backend=FakePlaybackBackend(tick_interval_ms=20),
            envelope_provider=envelope_provider,
            spectrum_service=spectrum_stub,  # type: ignore[arg-type]
            spectrum_params=SpectrumParams(band_count=48, hop_ms=32),
            should_sample_spectrum=lambda: False,
            waveform_proxy_service=wave_stub,  # type: ignore[arg-type]
            waveform_proxy_params=WaveformProxyParams(hop_ms=20),
            should_sample_waveform=lambda: False,
            beat_service=beat_stub,  # type: ignore[arg-type]
            beat_params=BeatParams(hop_ms=32),
            should_sample_beat=lambda: False,
            poll_interval_s=0.05,
        )
        play_item_latencies_ms: list[float] = []
        preload_event_latencies_ms: list[float] = []
        root = logging.getLogger()
        prior_level = root.level
        root.setLevel(logging.INFO)
        try:
            with capture_perf_events(
                logger=root,
                event_names={"analysis_preload_completed"},
            ) as capture:
                await service.start()
                try:
                    for item_id, path in enumerate(sample_files, start=1):
                        start = time.perf_counter()
                        await service.play_item(playlist_id=1, item_id=item_id)
                        play_item_latencies_ms.append(
                            (time.perf_counter() - start) * 1000.0
                        )
                        event = await wait_for_captured_event(
                            capture,
                            event_name="analysis_preload_completed",
                            context_equals={"track_path": str(path)},
                            timeout_s=2.0,
                        )
                        preload_event_latencies_ms.append(
                            event_latency_ms_since(start, event)
                        )
                    run = PerfRunResult(
                        run_id=f"player-switch-smoke-{uuid.uuid4().hex[:8]}",
                        created_at=utc_now_iso(),
                        app_version=None,
                        git_sha=None,
                        machine={"runner": "pytest-opt-in"},
                        config={
                            "scenario": "player_service_track_switch_preload_smoke",
                            "sample_tracks": len(sample_files),
                        },
                        scenarios=[
                            PerfScenarioResult(
                                scenario_id="warm_cache_track_play",
                                category="track_switch",
                                status="pass",
                                elapsed_s=sum(play_item_latencies_ms) / 1000.0,
                                metrics={
                                    "play_item_latency_ms": summarize_samples(
                                        play_item_latencies_ms,
                                        unit="ms",
                                    ),
                                    "analysis_preload_event_latency_ms": summarize_samples(
                                        preload_event_latencies_ms,
                                        unit="ms",
                                    ),
                                },
                                counters={"switch_count": len(sample_files)},
                                metadata={
                                    "stub_frame_counts": {
                                        "spectrum": 4096,
                                        "beat": 4096,
                                        "waveform_proxy": 6144,
                                        "envelope": 3000,
                                    },
                                    "corpus_manifest": build_perf_media_manifest(
                                        media_dir, probe_durations=False
                                    ),
                                    "tracks_used": [str(path) for path in sample_files],
                                },
                            )
                        ],
                    )
                    artifact_path = write_perf_run_artifact(
                        run, results_dir=tmp_path / "perf_results"
                    )
                finally:
                    await service.shutdown()
        finally:
            root.setLevel(prior_level)
        return play_item_latencies_ms, preload_event_latencies_ms, artifact_path

    play_item_latencies_ms, preload_event_latencies_ms, artifact_path = _run(
        run_scenario()
    )
    assert len(play_item_latencies_ms) == len(sample_files)
    assert len(preload_event_latencies_ms) == len(sample_files)
    assert max(play_item_latencies_ms) < 500.0
    assert max(preload_event_latencies_ms) < 2000.0
    assert artifact_path.exists()


def test_real_analysis_cache_cold_warm_benchmark_artifact(tmp_path) -> None:
    media_dir = resolve_perf_media_dir()
    skip_reason = perf_media_skip_reason(media_dir)
    if skip_reason is not None:
        pytest.skip(skip_reason)
    assert media_dir is not None

    corpus_files = sorted(
        (
            path
            for path in media_dir.rglob("*")
            if path.is_file()
            and path.suffix.lower() in {".mp3", ".flac", ".wav", ".ogg", ".m4a"}
        ),
        key=lambda path: path.stat().st_size,
    )
    if not corpus_files:
        pytest.skip("No audio files found in perf corpus.")
    track_path = corpus_files[0]
    track_path_str = str(track_path)

    spectrum_params = SpectrumParams(band_count=48, hop_ms=32)
    beat_params = BeatParams(hop_ms=32)
    waveform_params = WaveformProxyParams(hop_ms=20)

    class NoLiveProvider:
        async def get_level_sample(self):
            return None

    async def run_scenario() -> Path:
        db_path = tmp_path / "analysis_perf.sqlite"
        spectrum_store = SqliteSpectrumStore(db_path)
        beat_store = SqliteBeatStore(db_path)
        wave_store = SqliteWaveformProxyStore(db_path)
        envelope_store = SqliteEnvelopeStore(db_path, bucket_ms=50)

        await spectrum_store.initialize()
        await beat_store.initialize()
        await wave_store.initialize()
        await envelope_store.initialize()

        cold_metrics_samples: dict[str, list[float]] = {}
        warm_metrics_samples: dict[str, list[float]] = {}
        metadata: dict[str, object] = {
            "track_path": track_path_str,
            "track_size_bytes": track_path.stat().st_size,
        }

        start = time.perf_counter()
        bundle = analyze_track_analysis_bundle(
            track_path,
            spectrum_band_count=spectrum_params.band_count,
            spectrum_hop_ms=spectrum_params.hop_ms,
            beat_hop_ms=beat_params.hop_ms,
            waveform_hop_ms=waveform_params.hop_ms,
        )
        cold_metrics_samples["bundle_analyze_ms"] = [
            (time.perf_counter() - start) * 1000.0
        ]
        if bundle is None:
            pytest.skip(f"Unable to analyze track via shared bundle: {track_path}")
        assert bundle.spectrum is not None
        assert bundle.beat is not None
        assert bundle.waveform_proxy is not None

        start = time.perf_counter()
        await spectrum_store.upsert_spectrum(
            track_path,
            duration_ms=bundle.spectrum.duration_ms,
            params=spectrum_params,
            frames=bundle.spectrum.frames,
        )
        cold_metrics_samples["spectrum_upsert_ms"] = [
            (time.perf_counter() - start) * 1000.0
        ]

        start = time.perf_counter()
        await beat_store.upsert_beats(
            track_path,
            duration_ms=bundle.beat.duration_ms,
            params=beat_params,
            bpm=bundle.beat.bpm,
            frames=bundle.beat.frames,
        )
        cold_metrics_samples["beat_upsert_ms"] = [
            (time.perf_counter() - start) * 1000.0
        ]

        start = time.perf_counter()
        await wave_store.upsert_waveform_proxy(
            track_path,
            duration_ms=bundle.waveform_proxy.duration_ms,
            params=waveform_params,
            frames=bundle.waveform_proxy.frames,
        )
        cold_metrics_samples["waveform_upsert_ms"] = [
            (time.perf_counter() - start) * 1000.0
        ]

        envelope_result = None
        envelope_required_ffmpeg = requires_ffmpeg_for_envelope(track_path)
        metadata["envelope_requires_ffmpeg"] = envelope_required_ffmpeg
        metadata["ffmpeg_available"] = ffmpeg_available()
        if (not envelope_required_ffmpeg) or bool(metadata["ffmpeg_available"]):
            start = time.perf_counter()
            envelope_result = analyze_track_envelope(track_path, bucket_ms=50)
            cold_metrics_samples["envelope_analyze_ms"] = [
                (time.perf_counter() - start) * 1000.0
            ]
            if envelope_result is not None:
                start = time.perf_counter()
                await envelope_store.upsert_envelope(
                    track_path,
                    envelope_result.points,
                    duration_ms=envelope_result.duration_ms,
                )
                cold_metrics_samples["envelope_upsert_ms"] = [
                    (time.perf_counter() - start) * 1000.0
                ]

        spectrum_service = SpectrumService(cache_provider=spectrum_store)
        beat_service = BeatService(cache_provider=beat_store)
        wave_service = WaveformProxyService(cache_provider=wave_store)
        level_service = AudioLevelService(
            live_provider=NoLiveProvider(),
            envelope_provider=envelope_store,
        )

        sample_positions = [0, 250, 500, 1000, 2000, 4000, 8000, 12000]
        duration_ms = max(
            bundle.spectrum.duration_ms,
            bundle.beat.duration_ms,
            bundle.waveform_proxy.duration_ms,
            envelope_result.duration_ms if envelope_result is not None else 0,
        )
        sample_positions = [min(duration_ms, pos) for pos in sample_positions]

        for pos in sample_positions:
            start = time.perf_counter()
            spec = await spectrum_service.sample(
                track_path=track_path_str,
                position_ms=pos,
                params=spectrum_params,
            )
            warm_metrics_samples.setdefault("spectrum_db_sample_ms", []).append(
                (time.perf_counter() - start) * 1000.0
            )
            assert spec.status == "ready"

            start = time.perf_counter()
            beat = await beat_service.sample(
                track_path=track_path_str,
                position_ms=pos,
                params=beat_params,
            )
            warm_metrics_samples.setdefault("beat_db_sample_ms", []).append(
                (time.perf_counter() - start) * 1000.0
            )
            assert beat.status == "ready"

            start = time.perf_counter()
            wave = await wave_service.sample(
                track_path=track_path_str,
                position_ms=pos,
                params=waveform_params,
            )
            warm_metrics_samples.setdefault("waveform_db_sample_ms", []).append(
                (time.perf_counter() - start) * 1000.0
            )
            assert wave.status == "ready"

            if envelope_result is not None:
                start = time.perf_counter()
                level = await level_service.sample(
                    status="playing",
                    position_ms=pos,
                    duration_ms=duration_ms,
                    volume=50,
                    speed=1.0,
                    track_path=track_path_str,
                )
                warm_metrics_samples.setdefault("envelope_db_sample_ms", []).append(
                    (time.perf_counter() - start) * 1000.0
                )
                assert level is not None and level.status == "ready"

        start = time.perf_counter()
        preload_counts = {
            "spectrum": await spectrum_service.preload_track(
                track_path_str, params=spectrum_params
            ),
            "beat": await beat_service.preload_track(
                track_path_str, params=beat_params
            ),
            "waveform_proxy": await wave_service.preload_track(
                track_path_str, params=waveform_params
            ),
            "envelope": await level_service.preload_envelope_track(track_path_str),
        }
        warm_metrics_samples["memory_preload_all_ms"] = [
            (time.perf_counter() - start) * 1000.0
        ]

        for pos in sample_positions:
            start = time.perf_counter()
            spec = await spectrum_service.sample(
                track_path=track_path_str,
                position_ms=pos,
                params=spectrum_params,
            )
            warm_metrics_samples.setdefault("spectrum_memory_sample_ms", []).append(
                (time.perf_counter() - start) * 1000.0
            )
            assert spec.status == "ready"

            start = time.perf_counter()
            beat = await beat_service.sample(
                track_path=track_path_str,
                position_ms=pos,
                params=beat_params,
            )
            warm_metrics_samples.setdefault("beat_memory_sample_ms", []).append(
                (time.perf_counter() - start) * 1000.0
            )
            assert beat.status == "ready"

            start = time.perf_counter()
            wave = await wave_service.sample(
                track_path=track_path_str,
                position_ms=pos,
                params=waveform_params,
            )
            warm_metrics_samples.setdefault("waveform_memory_sample_ms", []).append(
                (time.perf_counter() - start) * 1000.0
            )
            assert wave.status == "ready"

            if envelope_result is not None:
                start = time.perf_counter()
                level = await level_service.sample(
                    status="playing",
                    position_ms=pos,
                    duration_ms=duration_ms,
                    volume=50,
                    speed=1.0,
                    track_path=track_path_str,
                )
                warm_metrics_samples.setdefault("envelope_memory_sample_ms", []).append(
                    (time.perf_counter() - start) * 1000.0
                )
                assert level is not None and level.status == "ready"

        metadata["frame_counts"] = {
            "spectrum": len(bundle.spectrum.frames),
            "beat": len(bundle.beat.frames),
            "waveform_proxy": len(bundle.waveform_proxy.frames),
            "envelope": 0 if envelope_result is None else len(envelope_result.points),
        }
        metadata["preload_counts"] = preload_counts
        metadata["corpus_manifest"] = build_perf_media_manifest(
            media_dir, probe_durations=False
        )

        run = PerfRunResult(
            run_id=f"analysis-cache-real-{uuid.uuid4().hex[:8]}",
            created_at=utc_now_iso(),
            app_version=None,
            git_sha=None,
            machine={"runner": "pytest-opt-in"},
            config={
                "scenario": "real_analysis_cache_cold_warm",
                "spectrum_hop_ms": spectrum_params.hop_ms,
                "beat_hop_ms": beat_params.hop_ms,
                "waveform_hop_ms": waveform_params.hop_ms,
            },
            scenarios=[
                PerfScenarioResult(
                    scenario_id="cold_cache_track_play",
                    category="analysis_cache",
                    status="pass",
                    elapsed_s=round(
                        sum(sum(values) for values in cold_metrics_samples.values())
                        / 1000.0,
                        6,
                    ),
                    metrics={
                        name: summarize_samples(samples, unit="ms")
                        for name, samples in cold_metrics_samples.items()
                    },
                    counters={
                        "sample_positions_count": len(sample_positions),
                    },
                    metadata=metadata,
                ),
                PerfScenarioResult(
                    scenario_id="warm_cache_track_play",
                    category="analysis_cache",
                    status="pass",
                    elapsed_s=round(
                        sum(sum(values) for values in warm_metrics_samples.values())
                        / 1000.0,
                        6,
                    ),
                    metrics={
                        name: summarize_samples(samples, unit="ms")
                        for name, samples in warm_metrics_samples.items()
                    },
                    counters={
                        "sample_positions_count": len(sample_positions),
                    },
                    metadata=metadata,
                ),
            ],
        )
        artifact_path = write_perf_run_artifact(
            run, results_dir=tmp_path / "perf_results"
        )
        return artifact_path

    artifact_path = _run(run_scenario())
    assert artifact_path.exists()


def test_controls_latency_jitter_under_background_load_benchmark(
    tmp_path, monkeypatch
) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    app = TzPlayerApp(auto_init=False, backend_name="fake")

    async def run_scenario() -> tuple[dict[str, list[float]], Path]:
        async with app.run_test():
            await asyncio.sleep(0)
            await app._initialize_state()

            stop_event = asyncio.Event()

            async def background_load() -> None:
                while not stop_event.is_set():
                    await run_cpu_bound(_cpu_spin, 80_000)
                    await asyncio.sleep(0)

            worker = asyncio.create_task(background_load())
            action_samples_ms: dict[str, list[float]] = {
                "volume_up_ms": [],
                "volume_down_ms": [],
                "speed_up_ms": [],
                "speed_reset_ms": [],
                "repeat_mode_ms": [],
                "shuffle_ms": [],
                "cycle_visualizer_ms": [],
            }
            action_steps = [
                ("volume_up_ms", app.action_volume_up),
                ("volume_down_ms", app.action_volume_down),
                ("speed_up_ms", app.action_speed_up),
                ("speed_reset_ms", app.action_speed_reset),
                ("repeat_mode_ms", app.action_repeat_mode),
                ("shuffle_ms", app.action_shuffle),
                ("cycle_visualizer_ms", app.action_cycle_visualizer),
            ]

            try:
                for _ in range(8):
                    for metric_name, action in action_steps:
                        start = time.perf_counter()
                        await action()
                        action_samples_ms[metric_name].append(
                            (time.perf_counter() - start) * 1000.0
                        )
                        await asyncio.sleep(0)
            finally:
                stop_event.set()
                worker.cancel()
                with suppress(asyncio.CancelledError):
                    await worker

            metrics = {
                metric_name: summarize_samples(samples, unit="ms")
                for metric_name, samples in action_samples_ms.items()
                if samples
            }
            jitter_counters = {
                f"{metric_name}_p95_minus_p50_ms": round(
                    summary.p95_value - summary.median_value,
                    4,
                )
                for metric_name, summary in metrics.items()
            }

            run = PerfRunResult(
                run_id=f"controls-jitter-{uuid.uuid4().hex[:8]}",
                created_at=utc_now_iso(),
                app_version=None,
                git_sha=None,
                machine={"runner": "pytest-opt-in"},
                config={
                    "scenario": "controls_latency_jitter_under_background_load",
                    "iterations": 8,
                    "background_load": "run_cpu_bound(_cpu_spin, 80000)",
                },
                scenarios=[
                    PerfScenarioResult(
                        scenario_id="controls_interaction_latency",
                        category="controls",
                        status="pass",
                        elapsed_s=round(
                            sum(sum(samples) for samples in action_samples_ms.values())
                            / 1000.0,
                            6,
                        ),
                        metrics=metrics,
                        counters={
                            "actions_per_type": 8,
                            "total_action_invocations": sum(
                                len(samples) for samples in action_samples_ms.values()
                            ),
                            **jitter_counters,
                        },
                        metadata={"visualizer_id": app._active_visualizer_id},
                    )
                ],
            )
            artifact_path = write_perf_run_artifact(
                run, results_dir=tmp_path / "perf_results"
            )
            app.exit()
            return action_samples_ms, artifact_path

    action_samples_ms, artifact_path = _run(run_scenario())
    assert artifact_path.exists()
    for samples in action_samples_ms.values():
        assert len(samples) == 8
        assert max(samples) < 1000.0


def test_hidden_hotspot_idle_and_control_burst_call_probe_artifact(
    tmp_path, monkeypatch
) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    app = TzPlayerApp(auto_init=False, backend_name="fake")

    async def run_scenario() -> Path:
        async with app.run_test():
            await asyncio.sleep(0)
            await app._initialize_state()
            await asyncio.sleep(0.2)

            targets: list[tuple[object, str, str | None]] = [
                (app, "_update_status_pane", "app.update_status_pane"),
                (app, "_update_current_track_pane", "app.update_current_track_pane"),
                (app, "_schedule_state_save", "app.schedule_state_save"),
                (app, "_save_state_debounced", "app.save_state_debounced"),
            ]
            player = getattr(app, "_player", None)
            if player is not None:
                targets.extend(
                    [
                        (player, "_emit_state", "player.emit_state"),
                        (player, "_poll_position", "player.poll_position"),
                    ]
                )

            with probe_method_calls(targets) as probe:
                idle_start = time.perf_counter()
                await asyncio.sleep(0.8)
                idle_elapsed_ms = (time.perf_counter() - idle_start) * 1000.0

                for _ in range(12):
                    await app.action_volume_up()
                    await app.action_volume_down()
                    await app.action_speed_up()
                    await app.action_speed_reset()
                    await app.action_repeat_mode()
                    await app.action_shuffle()
                    await app.action_cycle_visualizer()
                    await asyncio.sleep(0)

                await asyncio.sleep(0.4)
                stats = probe.snapshot()

            top_stats = stats[:10]
            metrics = {
                stat.name.replace(".", "_") + "_mean_ms": summarize_samples(
                    [stat.mean_s * 1000.0], unit="ms"
                )
                for stat in top_stats
            }
            counters: dict[str, int | float] = {
                "probed_method_count": len(stats),
                "idle_phase_elapsed_ms": round(idle_elapsed_ms, 3),
            }
            metadata_top: list[dict[str, object]] = []
            for stat in top_stats:
                key = stat.name.replace(".", "_")
                counters[f"{key}_count"] = stat.count
                counters[f"{key}_total_ms"] = round(stat.total_s * 1000.0, 4)
                counters[f"{key}_max_ms"] = round(stat.max_s * 1000.0, 4)
                metadata_top.append(
                    {
                        "name": stat.name,
                        "count": stat.count,
                        "total_ms": round(stat.total_s * 1000.0, 4),
                        "max_ms": round(stat.max_s * 1000.0, 4),
                        "mean_ms": round(stat.mean_s * 1000.0, 4),
                    }
                )

            run = PerfRunResult(
                run_id=f"hidden-hotspot-sweep-{uuid.uuid4().hex[:8]}",
                created_at=utc_now_iso(),
                app_version=None,
                git_sha=None,
                machine={"runner": "pytest-opt-in"},
                config={
                    "scenario": "hidden_hotspot_idle_and_control_burst_call_probe",
                    "idle_sleep_s": 0.8,
                    "control_iterations": 12,
                },
                scenarios=[
                    PerfScenarioResult(
                        scenario_id="hidden_hotspot_idle_playback_sweep",
                        category="hidden_hotspot",
                        status="pass",
                        elapsed_s=round((idle_elapsed_ms / 1000.0) + 0.4, 6),
                        metrics=metrics,
                        counters=counters,
                        metadata={
                            "top_cumulative_methods": metadata_top,
                            "visualizer_id": app._active_visualizer_id,
                        },
                    )
                ],
            )
            artifact_path = write_perf_run_artifact(
                run, results_dir=tmp_path / "perf_results"
            )
            app.exit()
            return artifact_path

    artifact_path = _run(run_scenario())
    assert artifact_path.exists()


def test_resource_usage_phase_trend_artifact(tmp_path, monkeypatch) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    app = TzPlayerApp(auto_init=False, backend_name="fake")

    async def run_scenario() -> Path:
        async with app.run_test():
            await asyncio.sleep(0)
            await app._initialize_state()
            snapshots = [capture_process_resource_snapshot(label="post_init")]

            await asyncio.sleep(0.4)
            snapshots.append(capture_process_resource_snapshot(label="after_idle"))

            for _ in range(10):
                await app.action_volume_up()
                await app.action_volume_down()
                await app.action_speed_up()
                await app.action_speed_reset()
                await app.action_cycle_visualizer()
                await asyncio.sleep(0)
            snapshots.append(capture_process_resource_snapshot(label="after_controls"))

            await asyncio.sleep(0.3)
            snapshots.append(capture_process_resource_snapshot(label="after_settle"))

            deltas = [
                diff_process_resource_snapshots(snapshots[idx], snapshots[idx + 1])
                for idx in range(len(snapshots) - 1)
            ]

            metrics = {}
            for delta in deltas:
                phase = f"{delta.start_label}_to_{delta.end_label}"
                metrics[f"{phase}_elapsed_ms"] = summarize_samples(
                    [delta.elapsed_s * 1000.0], unit="ms"
                )
                metrics[f"{phase}_process_cpu_ms"] = summarize_samples(
                    [delta.process_cpu_s * 1000.0], unit="ms"
                )
                if delta.thread_cpu_s is not None:
                    metrics[f"{phase}_thread_cpu_ms"] = summarize_samples(
                        [delta.thread_cpu_s * 1000.0], unit="ms"
                    )

            metadata_snapshots = [
                {
                    "label": snap.label,
                    "captured_monotonic_s": round(snap.captured_monotonic_s, 6),
                    "process_cpu_s": round(snap.process_cpu_s, 6),
                    "thread_cpu_s": None
                    if snap.thread_cpu_s is None
                    else round(snap.thread_cpu_s, 6),
                    "gc_counts": list(snap.gc_counts),
                    "gc_collections_total": snap.gc_collections_total,
                    "rss_bytes": snap.rss_bytes,
                }
                for snap in snapshots
            ]
            metadata_deltas = [
                {
                    "phase": f"{delta.start_label}_to_{delta.end_label}",
                    "elapsed_ms": round(delta.elapsed_s * 1000.0, 4),
                    "process_cpu_ms": round(delta.process_cpu_s * 1000.0, 4),
                    "thread_cpu_ms": None
                    if delta.thread_cpu_s is None
                    else round(delta.thread_cpu_s * 1000.0, 4),
                    "gc_count_deltas": list(delta.gc_count_deltas),
                    "gc_collections_delta": delta.gc_collections_delta,
                    "rss_bytes_delta": delta.rss_bytes_delta,
                }
                for delta in deltas
            ]

            run = PerfRunResult(
                run_id=f"resource-trend-{uuid.uuid4().hex[:8]}",
                created_at=utc_now_iso(),
                app_version=None,
                git_sha=None,
                machine={"runner": "pytest-opt-in"},
                config={
                    "scenario": "resource_usage_phase_trend",
                    "phases": [snap.label for snap in snapshots],
                },
                scenarios=[
                    PerfScenarioResult(
                        scenario_id="hidden_hotspot_browse_sweep",
                        category="resource_trend",
                        status="pass",
                        elapsed_s=round(sum(delta.elapsed_s for delta in deltas), 6),
                        metrics=metrics,
                        counters={
                            "snapshot_count": len(snapshots),
                            "delta_count": len(deltas),
                        },
                        metadata={
                            "snapshots": metadata_snapshots,
                            "deltas": metadata_deltas,
                            "visualizer_id": app._active_visualizer_id,
                        },
                    )
                ],
            )
            artifact_path = write_perf_run_artifact(
                run, results_dir=tmp_path / "perf_results"
            )
            app.exit()
            return artifact_path

    artifact_path = _run(run_scenario())
    assert artifact_path.exists()
