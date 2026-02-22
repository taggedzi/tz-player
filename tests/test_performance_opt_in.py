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
from tz_player.logging_utils import JsonLogFormatter
from tz_player.perf_benchmarking import (
    PerfRunResult,
    PerfScenarioResult,
    build_perf_media_manifest,
    perf_media_skip_reason,
    resolve_perf_media_dir,
    resolve_perf_results_dir,
    summarize_samples,
    utc_now_iso,
    write_perf_run_artifact,
)
from tz_player.perf_observability import (
    EventContextCountSpec,
    EventNumericSummarySpec,
    capture_perf_events,
    capture_process_resource_snapshot,
    count_events_by_context_value,
    count_events_by_name,
    diff_process_resource_snapshots,
    event_latency_ms_since,
    probe_method_calls,
    summarize_captured_events,
    summarize_numeric_event_context,
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
LOCAL_CORPUS_VARIETY_TRACK_COUNT = 10
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


def _perf_results_dir(tmp_path: Path) -> Path:
    """Use env-configured perf artifact dir when provided, else test-local dir."""
    if os.getenv("TZ_PLAYER_PERF_RESULTS_DIR"):
        return resolve_perf_results_dir()
    return tmp_path / "perf_results"


def _local_perf_corpus_audio_files(media_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in media_dir.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".mp3", ".flac", ".wav", ".ogg", ".m4a"}
    )


def _select_varied_tracks_by_size(
    corpus_files: list[Path], *, target_count: int = LOCAL_CORPUS_VARIETY_TRACK_COUNT
) -> list[Path]:
    """Pick a size-stratified subset of tracks for varied perf coverage."""
    if not corpus_files:
        return []
    sorted_files = sorted(
        corpus_files, key=lambda path: (path.stat().st_size, str(path))
    )
    count = min(max(1, int(target_count)), len(sorted_files))
    if count == len(sorted_files):
        return sorted_files

    chosen_indices: set[int] = set()
    if count == 1:
        chosen_indices.add(len(sorted_files) // 2)
    else:
        max_index = len(sorted_files) - 1
        for slot in range(count):
            idx = round((slot * max_index) / (count - 1))
            chosen_indices.add(int(idx))
        # Fill gaps if rounding collapsed indices.
        cursor = 0
        while len(chosen_indices) < count and cursor < len(sorted_files):
            chosen_indices.add(cursor)
            cursor += 1
    return [sorted_files[idx] for idx in sorted(chosen_indices)]


def _active_visualizer_id(app: TzPlayerApp) -> str | None:
    """Best-effort active visualizer id across app implementation revisions."""
    host = getattr(app, "visualizer_host", None)
    host_active = getattr(host, "active_id", None)
    if isinstance(host_active, str) and host_active:
        return host_active
    state = getattr(app, "state", None)
    state_active = getattr(state, "visualizer_id", None)
    if isinstance(state_active, str) and state_active:
        return state_active
    return None


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

    event_summary = summarize_captured_events(
        slow_events,
        context_count_specs=[
            EventContextCountSpec(
                event_name="playlist_store_slow_query",
                context_key="operation",
                alias="slow_ops",
            ),
            EventContextCountSpec(
                event_name="playlist_store_slow_query",
                context_key="mode",
                alias="slow_modes",
            ),
        ],
        numeric_summary_specs=[
            EventNumericSummarySpec(
                event_name="playlist_store_slow_query",
                context_key="elapsed_ms",
                alias="slow_elapsed_ms",
            )
        ],
    )
    event_counts = count_events_by_name(slow_events)
    slow_ops = count_events_by_context_value(
        slow_events,
        event_name="playlist_store_slow_query",
        context_key="operation",
    )
    slow_modes = count_events_by_context_value(
        slow_events,
        event_name="playlist_store_slow_query",
        context_key="mode",
    )
    slow_elapsed_summary = summarize_numeric_event_context(
        slow_events,
        event_name="playlist_store_slow_query",
        context_key="elapsed_ms",
    )

    metrics = {
        metric_name: summarize_samples(samples, unit="ms")
        for metric_name, samples in timings_ms.items()
    }
    if slow_elapsed_summary is not None:
        metrics["slow_query_event_elapsed_ms"] = summarize_samples(
            [
                slow_elapsed_summary.min_value,
                slow_elapsed_summary.mean_value,
                slow_elapsed_summary.max_value,
            ],
            unit="ms",
        )
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
                    "event_summary": event_summary,
                    "slow_operation_counts": slow_ops,
                    "slow_mode_counts": slow_modes,
                    "captured_event_names": event_counts,
                    "slow_elapsed_summary": None
                    if slow_elapsed_summary is None
                    else {
                        "count": slow_elapsed_summary.count,
                        "min_value": slow_elapsed_summary.min_value,
                        "mean_value": slow_elapsed_summary.mean_value,
                        "max_value": slow_elapsed_summary.max_value,
                    },
                },
            )
        ],
    )
    artifact_path = write_perf_run_artifact(
        run, results_dir=_perf_results_dir(tmp_path)
    )
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
    artifact_path = write_perf_run_artifact(
        run, results_dir=_perf_results_dir(tmp_path)
    )
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

    corpus_files = _local_perf_corpus_audio_files(media_dir)
    if len(corpus_files) < 3:
        pytest.skip("Need at least 3 audio files in perf corpus for switch benchmark.")
    sample_files = _select_varied_tracks_by_size(corpus_files, target_count=10)

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
                                    "track_selection_mode": "size_stratified",
                                    "tracks_used": [str(path) for path in sample_files],
                                },
                            )
                        ],
                    )
                    artifact_path = write_perf_run_artifact(
                        run, results_dir=_perf_results_dir(tmp_path)
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

    corpus_files = _local_perf_corpus_audio_files(media_dir)
    if not corpus_files:
        pytest.skip("No audio files found in perf corpus.")
    sample_tracks = _select_varied_tracks_by_size(corpus_files, target_count=10)
    if not sample_tracks:
        pytest.skip("No sample tracks selected from perf corpus.")

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
        spectrum_service = SpectrumService(cache_provider=spectrum_store)
        beat_service = BeatService(cache_provider=beat_store)
        wave_service = WaveformProxyService(cache_provider=wave_store)
        level_service = AudioLevelService(
            live_provider=NoLiveProvider(),
            envelope_provider=envelope_store,
        )

        ffmpeg_ok = ffmpeg_available()
        track_metadata: list[dict[str, object]] = []
        total_sample_positions = 0
        analysis_backend_counts: dict[str, int] = {}
        beat_backend_counts: dict[str, int] = {}
        waveform_backend_counts: dict[str, int] = {}
        analysis_fallback_reason_counts: dict[str, int] = {}
        native_helper_cmd = os.getenv("TZ_PLAYER_NATIVE_SPECTRUM_HELPER_CMD")
        native_helper_timeout_s = os.getenv("TZ_PLAYER_NATIVE_SPECTRUM_HELPER_TIMEOUT_S")

        for track_path in sample_tracks:
            track_path_str = str(track_path)
            per_track_meta: dict[str, object] = {
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
            cold_metrics_samples.setdefault("bundle_analyze_ms", []).append(
                (time.perf_counter() - start) * 1000.0
            )
            if bundle is None:
                continue
            assert bundle.spectrum is not None
            assert bundle.beat is not None
            assert bundle.waveform_proxy is not None
            if bundle.backend_info is not None:
                per_track_meta["analysis_backend"] = bundle.backend_info.analysis_backend
                if bundle.backend_info.spectrum_backend is not None:
                    per_track_meta["spectrum_backend"] = (
                        bundle.backend_info.spectrum_backend
                    )
                if bundle.backend_info.beat_backend is not None:
                    per_track_meta["beat_backend"] = bundle.backend_info.beat_backend
                    beat_backend = bundle.backend_info.beat_backend
                    beat_backend_counts[beat_backend] = (
                        beat_backend_counts.get(beat_backend, 0) + 1
                    )
                if bundle.backend_info.waveform_proxy_backend is not None:
                    per_track_meta["waveform_proxy_backend"] = (
                        bundle.backend_info.waveform_proxy_backend
                    )
                    wave_backend = bundle.backend_info.waveform_proxy_backend
                    waveform_backend_counts[wave_backend] = (
                        waveform_backend_counts.get(wave_backend, 0) + 1
                    )
                if bundle.backend_info.fallback_reason is not None:
                    per_track_meta["analysis_fallback_reason"] = (
                        bundle.backend_info.fallback_reason
                    )
                if bundle.backend_info.native_helper_version is not None:
                    per_track_meta["native_helper_version"] = (
                        bundle.backend_info.native_helper_version
                    )
                per_track_meta["duplicate_decode_for_mixed_bundle"] = (
                    bundle.backend_info.duplicate_decode_for_mixed_bundle
                )
                analysis_backend_counts[bundle.backend_info.analysis_backend] = (
                    analysis_backend_counts.get(bundle.backend_info.analysis_backend, 0)
                    + 1
                )
                if bundle.backend_info.fallback_reason is not None:
                    reason = bundle.backend_info.fallback_reason
                    analysis_fallback_reason_counts[reason] = (
                        analysis_fallback_reason_counts.get(reason, 0) + 1
                    )
            if bundle.timings is not None:
                per_track_meta["bundle_timings_ms"] = {
                    "decode_ms": round(bundle.timings.decode_ms, 3),
                    "python_decode_ms": round(bundle.timings.python_decode_ms, 3),
                    "native_helper_decode_ms": round(
                        bundle.timings.native_helper_decode_ms, 3
                    ),
                    "native_helper_total_ms": round(
                        bundle.timings.native_helper_total_ms, 3
                    ),
                    "spectrum_ms": round(bundle.timings.spectrum_ms, 3),
                    "beat_ms": round(bundle.timings.beat_ms, 3),
                    "waveform_ms": round(bundle.timings.waveform_proxy_ms, 3),
                    "total_ms": round(bundle.timings.total_ms, 3),
                }
                cold_metrics_samples.setdefault("bundle_decode_ms", []).append(
                    bundle.timings.decode_ms
                )
                cold_metrics_samples.setdefault("bundle_python_decode_ms", []).append(
                    bundle.timings.python_decode_ms
                )
                cold_metrics_samples.setdefault(
                    "bundle_native_helper_decode_ms", []
                ).append(bundle.timings.native_helper_decode_ms)
                cold_metrics_samples.setdefault(
                    "bundle_native_helper_total_ms", []
                ).append(bundle.timings.native_helper_total_ms)
                cold_metrics_samples.setdefault("bundle_spectrum_ms", []).append(
                    bundle.timings.spectrum_ms
                )
                cold_metrics_samples.setdefault("bundle_beat_ms", []).append(
                    bundle.timings.beat_ms
                )
                cold_metrics_samples.setdefault("bundle_waveform_ms", []).append(
                    bundle.timings.waveform_proxy_ms
                )
                cold_metrics_samples.setdefault("bundle_total_ms", []).append(
                    bundle.timings.total_ms
                )

            start = time.perf_counter()
            await spectrum_store.upsert_spectrum(
                track_path,
                duration_ms=bundle.spectrum.duration_ms,
                params=spectrum_params,
                frames=bundle.spectrum.frames,
            )
            cold_metrics_samples.setdefault("spectrum_upsert_ms", []).append(
                (time.perf_counter() - start) * 1000.0
            )

            start = time.perf_counter()
            await beat_store.upsert_beats(
                track_path,
                duration_ms=bundle.beat.duration_ms,
                params=beat_params,
                bpm=bundle.beat.bpm,
                frames=bundle.beat.frames,
            )
            cold_metrics_samples.setdefault("beat_upsert_ms", []).append(
                (time.perf_counter() - start) * 1000.0
            )

            start = time.perf_counter()
            await wave_store.upsert_waveform_proxy(
                track_path,
                duration_ms=bundle.waveform_proxy.duration_ms,
                params=waveform_params,
                frames=bundle.waveform_proxy.frames,
            )
            cold_metrics_samples.setdefault("waveform_upsert_ms", []).append(
                (time.perf_counter() - start) * 1000.0
            )

            envelope_result = None
            envelope_required_ffmpeg = requires_ffmpeg_for_envelope(track_path)
            per_track_meta["envelope_requires_ffmpeg"] = envelope_required_ffmpeg
            if (not envelope_required_ffmpeg) or ffmpeg_ok:
                start = time.perf_counter()
                envelope_result = analyze_track_envelope(track_path, bucket_ms=50)
                cold_metrics_samples.setdefault("envelope_analyze_ms", []).append(
                    (time.perf_counter() - start) * 1000.0
                )
                if envelope_result is not None:
                    start = time.perf_counter()
                    await envelope_store.upsert_envelope(
                        track_path,
                        envelope_result.points,
                        duration_ms=envelope_result.duration_ms,
                    )
                    cold_metrics_samples.setdefault("envelope_upsert_ms", []).append(
                        (time.perf_counter() - start) * 1000.0
                    )

            sample_positions = [0, 250, 500, 1000, 2000, 4000, 8000, 12000]
            duration_ms = max(
                bundle.spectrum.duration_ms,
                bundle.beat.duration_ms,
                bundle.waveform_proxy.duration_ms,
                envelope_result.duration_ms if envelope_result is not None else 0,
            )
            sample_positions = [min(duration_ms, pos) for pos in sample_positions]
            total_sample_positions += len(sample_positions)

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
            warm_metrics_samples.setdefault("memory_preload_all_ms", []).append(
                (time.perf_counter() - start) * 1000.0
            )

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
                    warm_metrics_samples.setdefault(
                        "envelope_memory_sample_ms", []
                    ).append((time.perf_counter() - start) * 1000.0)
                    assert level is not None and level.status == "ready"

            per_track_meta["frame_counts"] = {
                "spectrum": len(bundle.spectrum.frames),
                "beat": len(bundle.beat.frames),
                "waveform_proxy": len(bundle.waveform_proxy.frames),
                "envelope": 0
                if envelope_result is None
                else len(envelope_result.points),
            }
            per_track_meta["preload_counts"] = preload_counts
            per_track_meta["duration_ms"] = duration_ms
            track_metadata.append(per_track_meta)

        if not cold_metrics_samples.get("bundle_analyze_ms"):
            pytest.skip("Unable to analyze any selected tracks via shared bundle.")

        metadata: dict[str, object] = {
            "track_selection_mode": "size_stratified",
            "tracks_requested": len(sample_tracks),
            "tracks_analyzed": len(track_metadata),
            "ffmpeg_available": ffmpeg_ok,
            "tracks": track_metadata,
            "analysis_backend_counts": dict(sorted(analysis_backend_counts.items())),
        }
        if beat_backend_counts:
            metadata["beat_backend_counts"] = dict(sorted(beat_backend_counts.items()))
        if waveform_backend_counts:
            metadata["waveform_proxy_backend_counts"] = dict(
                sorted(waveform_backend_counts.items())
            )
        if native_helper_cmd:
            metadata["native_helper_cmd"] = native_helper_cmd
        if native_helper_timeout_s:
            metadata["native_helper_timeout_s"] = native_helper_timeout_s
        if analysis_fallback_reason_counts:
            metadata["analysis_fallback_reason_counts"] = dict(
                sorted(analysis_fallback_reason_counts.items())
            )
        metadata["corpus_manifest"] = build_perf_media_manifest(
            media_dir, probe_durations=False
        )
        cold_elapsed_metric_names = set(cold_metrics_samples)
        if "bundle_total_ms" in cold_elapsed_metric_names:
            cold_elapsed_metric_names.discard("bundle_analyze_ms")
            cold_elapsed_metric_names.discard("bundle_decode_ms")
            cold_elapsed_metric_names.discard("bundle_spectrum_ms")
            cold_elapsed_metric_names.discard("bundle_beat_ms")
            cold_elapsed_metric_names.discard("bundle_waveform_ms")
        elif "bundle_analyze_ms" in cold_elapsed_metric_names:
            cold_elapsed_metric_names.discard("bundle_decode_ms")
            cold_elapsed_metric_names.discard("bundle_spectrum_ms")
            cold_elapsed_metric_names.discard("bundle_beat_ms")
            cold_elapsed_metric_names.discard("bundle_waveform_ms")
        cold_elapsed_ms = sum(
            sum(cold_metrics_samples[name])
            for name in sorted(cold_elapsed_metric_names)
        )
        warm_elapsed_ms = sum(sum(values) for values in warm_metrics_samples.values())

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
                    elapsed_s=round(cold_elapsed_ms / 1000.0, 6),
                    metrics={
                        name: summarize_samples(samples, unit="ms")
                        for name, samples in cold_metrics_samples.items()
                    },
                    counters={
                        "tracks_requested": len(sample_tracks),
                        "tracks_analyzed": len(track_metadata),
                        "sample_positions_count": total_sample_positions,
                        "analysis_backend_python_tracks": analysis_backend_counts.get(
                            "python", 0
                        ),
                        "analysis_backend_native_helper_tracks": (
                            analysis_backend_counts.get("native_helper", 0)
                        ),
                        "analysis_backend_hybrid_tracks": (
                            analysis_backend_counts.get(
                                "hybrid_native_spectrum_python_rest", 0
                            )
                        ),
                    },
                    metadata=metadata,
                ),
                PerfScenarioResult(
                    scenario_id="warm_cache_track_play",
                    category="analysis_cache",
                    status="pass",
                    elapsed_s=round(warm_elapsed_ms / 1000.0, 6),
                    metrics={
                        name: summarize_samples(samples, unit="ms")
                        for name, samples in warm_metrics_samples.items()
                    },
                    counters={
                        "tracks_requested": len(sample_tracks),
                        "tracks_analyzed": len(track_metadata),
                        "sample_positions_count": total_sample_positions,
                        "analysis_backend_python_tracks": analysis_backend_counts.get(
                            "python", 0
                        ),
                        "analysis_backend_native_helper_tracks": (
                            analysis_backend_counts.get("native_helper", 0)
                        ),
                        "analysis_backend_hybrid_tracks": (
                            analysis_backend_counts.get(
                                "hybrid_native_spectrum_python_rest", 0
                            )
                        ),
                    },
                    metadata=metadata,
                ),
            ],
        )
        artifact_path = write_perf_run_artifact(
            run, results_dir=_perf_results_dir(tmp_path)
        )
        return artifact_path

    artifact_path = _run(run_scenario())
    assert artifact_path.exists()


def test_real_analysis_bundle_spectrum_waveform_cold_benchmark_artifact(tmp_path) -> None:
    media_dir = resolve_perf_media_dir()
    skip_reason = perf_media_skip_reason(media_dir)
    if skip_reason is not None:
        pytest.skip(skip_reason)
    assert media_dir is not None

    corpus_files = _local_perf_corpus_audio_files(media_dir)
    if not corpus_files:
        pytest.skip("No audio files found in perf corpus.")
    sample_tracks = _select_varied_tracks_by_size(corpus_files, target_count=10)
    if not sample_tracks:
        pytest.skip("No sample tracks selected from perf corpus.")

    spectrum_params = SpectrumParams(band_count=48, hop_ms=32)
    waveform_params = WaveformProxyParams(hop_ms=20)

    async def run_scenario() -> Path:
        cold_metrics_samples: dict[str, list[float]] = {}
        ffmpeg_ok = ffmpeg_available()
        track_metadata: list[dict[str, object]] = []
        analysis_backend_counts: dict[str, int] = {}
        beat_backend_counts: dict[str, int] = {}
        waveform_backend_counts: dict[str, int] = {}
        analysis_fallback_reason_counts: dict[str, int] = {}
        native_helper_cmd = os.getenv("TZ_PLAYER_NATIVE_SPECTRUM_HELPER_CMD")
        native_helper_timeout_s = os.getenv("TZ_PLAYER_NATIVE_SPECTRUM_HELPER_TIMEOUT_S")

        for track_path in sample_tracks:
            per_track_meta: dict[str, object] = {
                "track_path": str(track_path),
                "track_size_bytes": track_path.stat().st_size,
            }
            start = time.perf_counter()
            bundle = analyze_track_analysis_bundle(
                track_path,
                spectrum_band_count=spectrum_params.band_count,
                spectrum_hop_ms=spectrum_params.hop_ms,
                beat_hop_ms=spectrum_params.hop_ms,
                waveform_hop_ms=waveform_params.hop_ms,
                include_beat=False,
                include_waveform_proxy=True,
            )
            cold_metrics_samples.setdefault("bundle_analyze_ms", []).append(
                (time.perf_counter() - start) * 1000.0
            )
            if bundle is None:
                continue
            assert bundle.spectrum is not None
            assert bundle.waveform_proxy is not None
            assert bundle.beat is None

            if bundle.backend_info is not None:
                per_track_meta["analysis_backend"] = bundle.backend_info.analysis_backend
                if bundle.backend_info.spectrum_backend is not None:
                    per_track_meta["spectrum_backend"] = bundle.backend_info.spectrum_backend
                if bundle.backend_info.waveform_proxy_backend is not None:
                    per_track_meta["waveform_proxy_backend"] = (
                        bundle.backend_info.waveform_proxy_backend
                    )
                    wave_backend = bundle.backend_info.waveform_proxy_backend
                    waveform_backend_counts[wave_backend] = (
                        waveform_backend_counts.get(wave_backend, 0) + 1
                    )
                if bundle.backend_info.beat_backend is not None:
                    per_track_meta["beat_backend"] = bundle.backend_info.beat_backend
                    beat_backend = bundle.backend_info.beat_backend
                    beat_backend_counts[beat_backend] = (
                        beat_backend_counts.get(beat_backend, 0) + 1
                    )
                if bundle.backend_info.fallback_reason is not None:
                    per_track_meta["analysis_fallback_reason"] = (
                        bundle.backend_info.fallback_reason
                    )
                    reason = bundle.backend_info.fallback_reason
                    analysis_fallback_reason_counts[reason] = (
                        analysis_fallback_reason_counts.get(reason, 0) + 1
                    )
                if bundle.backend_info.native_helper_version is not None:
                    per_track_meta["native_helper_version"] = (
                        bundle.backend_info.native_helper_version
                    )
                per_track_meta["duplicate_decode_for_mixed_bundle"] = (
                    bundle.backend_info.duplicate_decode_for_mixed_bundle
                )
                backend = bundle.backend_info.analysis_backend
                analysis_backend_counts[backend] = analysis_backend_counts.get(backend, 0) + 1

            if bundle.timings is not None:
                per_track_meta["bundle_timings_ms"] = {
                    "decode_ms": round(bundle.timings.decode_ms, 3),
                    "python_decode_ms": round(bundle.timings.python_decode_ms, 3),
                    "native_helper_decode_ms": round(
                        bundle.timings.native_helper_decode_ms, 3
                    ),
                    "native_helper_total_ms": round(
                        bundle.timings.native_helper_total_ms, 3
                    ),
                    "spectrum_ms": round(bundle.timings.spectrum_ms, 3),
                    "waveform_ms": round(bundle.timings.waveform_proxy_ms, 3),
                    "total_ms": round(bundle.timings.total_ms, 3),
                }
                cold_metrics_samples.setdefault("bundle_decode_ms", []).append(
                    bundle.timings.decode_ms
                )
                cold_metrics_samples.setdefault("bundle_python_decode_ms", []).append(
                    bundle.timings.python_decode_ms
                )
                cold_metrics_samples.setdefault(
                    "bundle_native_helper_decode_ms", []
                ).append(bundle.timings.native_helper_decode_ms)
                cold_metrics_samples.setdefault(
                    "bundle_native_helper_total_ms", []
                ).append(bundle.timings.native_helper_total_ms)
                cold_metrics_samples.setdefault("bundle_spectrum_ms", []).append(
                    bundle.timings.spectrum_ms
                )
                cold_metrics_samples.setdefault("bundle_waveform_ms", []).append(
                    bundle.timings.waveform_proxy_ms
                )
                cold_metrics_samples.setdefault("bundle_total_ms", []).append(
                    bundle.timings.total_ms
                )

            per_track_meta["frame_counts"] = {
                "spectrum": len(bundle.spectrum.frames),
                "waveform_proxy": len(bundle.waveform_proxy.frames),
            }
            per_track_meta["duration_ms"] = max(
                bundle.spectrum.duration_ms, bundle.waveform_proxy.duration_ms
            )
            track_metadata.append(per_track_meta)

        if not cold_metrics_samples.get("bundle_analyze_ms"):
            pytest.skip("Unable to analyze any selected tracks via shared bundle.")

        metadata: dict[str, object] = {
            "track_selection_mode": "size_stratified",
            "tracks_requested": len(sample_tracks),
            "tracks_analyzed": len(track_metadata),
            "ffmpeg_available": ffmpeg_ok,
            "tracks": track_metadata,
            "analysis_backend_counts": dict(sorted(analysis_backend_counts.items())),
            "waveform_proxy_backend_counts": dict(sorted(waveform_backend_counts.items())),
            "bundle_request_shape": "spectrum_plus_waveform_no_beat",
        }
        if beat_backend_counts:
            metadata["beat_backend_counts"] = dict(sorted(beat_backend_counts.items()))
        if native_helper_cmd:
            metadata["native_helper_cmd"] = native_helper_cmd
        if native_helper_timeout_s:
            metadata["native_helper_timeout_s"] = native_helper_timeout_s
        if analysis_fallback_reason_counts:
            metadata["analysis_fallback_reason_counts"] = dict(
                sorted(analysis_fallback_reason_counts.items())
            )
        metadata["corpus_manifest"] = build_perf_media_manifest(
            media_dir, probe_durations=False
        )

        cold_elapsed_metric_names = set(cold_metrics_samples)
        if "bundle_total_ms" in cold_elapsed_metric_names:
            cold_elapsed_metric_names.discard("bundle_analyze_ms")
            cold_elapsed_metric_names.discard("bundle_decode_ms")
            cold_elapsed_metric_names.discard("bundle_spectrum_ms")
            cold_elapsed_metric_names.discard("bundle_waveform_ms")
        elif "bundle_analyze_ms" in cold_elapsed_metric_names:
            cold_elapsed_metric_names.discard("bundle_decode_ms")
            cold_elapsed_metric_names.discard("bundle_spectrum_ms")
            cold_elapsed_metric_names.discard("bundle_waveform_ms")
        cold_elapsed_ms = sum(
            sum(cold_metrics_samples[name])
            for name in sorted(cold_elapsed_metric_names)
        )

        run = PerfRunResult(
            run_id=f"analysis-bundle-sw-real-{uuid.uuid4().hex[:8]}",
            created_at=utc_now_iso(),
            app_version=None,
            git_sha=None,
            machine={"runner": "pytest-opt-in"},
            config={
                "scenario": "real_analysis_bundle_spectrum_waveform_cold",
                "spectrum_hop_ms": spectrum_params.hop_ms,
                "waveform_hop_ms": waveform_params.hop_ms,
                "include_beat": False,
            },
            scenarios=[
                PerfScenarioResult(
                    scenario_id="cold_bundle_spectrum_waveform",
                    category="analysis_bundle",
                    status="pass",
                    elapsed_s=round(cold_elapsed_ms / 1000.0, 6),
                    metrics={
                        name: summarize_samples(samples, unit="ms")
                        for name, samples in cold_metrics_samples.items()
                    },
                    counters={
                        "tracks_requested": len(sample_tracks),
                        "tracks_analyzed": len(track_metadata),
                        "analysis_backend_python_tracks": analysis_backend_counts.get(
                            "python", 0
                        ),
                        "analysis_backend_native_helper_tracks": (
                            analysis_backend_counts.get("native_helper", 0)
                        ),
                        "analysis_backend_hybrid_tracks": (
                            analysis_backend_counts.get(
                                "hybrid_native_spectrum_python_rest", 0
                            )
                        ),
                    },
                    metadata=metadata,
                )
            ],
        )
        artifact_path = write_perf_run_artifact(
            run, results_dir=_perf_results_dir(tmp_path)
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
                        metadata={"visualizer_id": _active_visualizer_id(app)},
                    )
                ],
            )
            artifact_path = write_perf_run_artifact(
                run, results_dir=_perf_results_dir(tmp_path)
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
                            "visualizer_id": _active_visualizer_id(app),
                        },
                    )
                ],
            )
            artifact_path = write_perf_run_artifact(
                run, results_dir=_perf_results_dir(tmp_path)
            )
            app.exit()
            return artifact_path

    artifact_path = _run(run_scenario())
    assert artifact_path.exists()


def test_hidden_hotspot_state_save_and_logging_overhead_artifact(
    tmp_path, monkeypatch
) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    app = TzPlayerApp(auto_init=False, backend_name="fake")

    async def run_scenario() -> Path:
        async with app.run_test():
            await asyncio.sleep(0)
            await app._initialize_state()

            formatter = JsonLogFormatter()
            state_save_samples_ms: list[float] = []
            log_format_samples_ms: list[float] = []
            formatted_bytes: list[int] = []

            probe_targets: list[tuple[object, str, str | None]] = [
                (app, "_save_state_snapshot", "app.save_state_snapshot"),
                (formatter, "format", "logging.json_formatter.format"),
            ]
            with probe_method_calls(probe_targets) as probe:
                for _ in range(10):
                    start = time.perf_counter()
                    await app._save_state_snapshot(app.state)
                    state_save_samples_ms.append((time.perf_counter() - start) * 1000.0)

                for idx in range(300):
                    record = logging.makeLogRecord(
                        {
                            "name": "tz_player.perf.synthetic",
                            "levelno": logging.INFO,
                            "levelname": "INFO",
                            "msg": "Synthetic perf event %s",
                            "args": (idx,),
                            "event": "synthetic_perf_event",
                            "context_id": idx % 7,
                            "payload": {
                                "idx": idx,
                                "bucket": idx % 11,
                                "values": [idx, idx + 1, idx + 2],
                            },
                        }
                    )
                    start = time.perf_counter()
                    rendered = formatter.format(record)
                    log_format_samples_ms.append((time.perf_counter() - start) * 1000.0)
                    formatted_bytes.append(len(rendered.encode("utf-8")))

                probe_stats = probe.snapshot()

            top_stats = probe_stats[:10]
            metadata_top = [
                {
                    "name": stat.name,
                    "count": stat.count,
                    "total_ms": round(stat.total_s * 1000.0, 4),
                    "max_ms": round(stat.max_s * 1000.0, 4),
                    "mean_ms": round(stat.mean_s * 1000.0, 4),
                }
                for stat in top_stats
            ]
            metrics = {
                "state_save_snapshot_ms": summarize_samples(
                    state_save_samples_ms, unit="ms"
                ),
                "json_log_format_ms": summarize_samples(
                    log_format_samples_ms, unit="ms"
                ),
                "json_log_output_bytes": summarize_samples(
                    [float(value) for value in formatted_bytes], unit="bytes"
                ),
            }

            run = PerfRunResult(
                run_id=f"hidden-hotspot-save-log-{uuid.uuid4().hex[:8]}",
                created_at=utc_now_iso(),
                app_version=None,
                git_sha=None,
                machine={"runner": "pytest-opt-in"},
                config={
                    "scenario": "hidden_hotspot_state_save_and_logging_overhead",
                    "state_save_iterations": 10,
                    "log_format_iterations": 300,
                },
                scenarios=[
                    PerfScenarioResult(
                        scenario_id="hidden_hotspot_browse_sweep",
                        category="hidden_hotspot",
                        status="pass",
                        elapsed_s=round(
                            (sum(state_save_samples_ms) + sum(log_format_samples_ms))
                            / 1000.0,
                            6,
                        ),
                        metrics=metrics,
                        counters={
                            "state_save_iterations": 10,
                            "log_format_iterations": 300,
                            "probed_method_count": len(probe_stats),
                            "top_cumulative_methods_count": len(top_stats),
                        },
                        metadata={
                            "top_cumulative_methods": metadata_top,
                            "visualizer_id": _active_visualizer_id(app),
                        },
                    )
                ],
            )
            artifact_path = write_perf_run_artifact(
                run, results_dir=_perf_results_dir(tmp_path)
            )
            app.exit()
            return artifact_path

    artifact_path = _run(run_scenario())
    assert artifact_path.exists()


def test_hidden_hotspot_frame_input_and_host_render_overhead_artifact(tmp_path) -> None:
    registry = VisualizerRegistry.built_in()
    context = VisualizerContext(ansi_enabled=False, unicode_enabled=True)
    spectrum = bytes(((idx * 13) % 256) for idx in range(48))

    def run_scenario() -> Path:
        host = VisualizerHost(registry, target_fps=12)
        host.activate("basic", context)
        build_samples_ms: list[float] = []
        render_samples_ms: list[float] = []
        combined_samples_ms: list[float] = []
        throttled = 0
        outputs = 0

        with probe_method_calls(
            [(host, "render_frame", "visualizer_host.render_frame")]
        ) as probe:
            for frame_idx in range(240):
                frame_start = time.perf_counter()

                build_start = time.perf_counter()
                frame = VisualizerFrameInput(
                    frame_index=frame_idx,
                    monotonic_s=frame_idx / 60.0,
                    width=120,
                    height=34,
                    status="playing",
                    position_s=frame_idx * 0.05,
                    duration_s=180.0,
                    volume=65.0,
                    speed=1.0,
                    repeat_mode="OFF",
                    shuffle=False,
                    track_id=1,
                    track_path="/perf/frame-build.mp3",
                    title="Perf Frame Build",
                    artist="Bench",
                    album="Bench",
                    level_left=0.45 + ((frame_idx % 7) * 0.01),
                    level_right=0.41 + ((frame_idx % 5) * 0.01),
                    level_source="cache",
                    level_status="ready",
                    spectrum_bands=spectrum,
                    spectrum_source="cache",
                    spectrum_status="ready",
                    waveform_min_left=-0.5,
                    waveform_max_left=0.7,
                    waveform_min_right=-0.45,
                    waveform_max_right=0.66,
                    waveform_source="cache",
                    waveform_status="ready",
                    beat_strength=0.8 if frame_idx % 24 == 0 else 0.2,
                    beat_is_onset=(frame_idx % 24 == 0),
                    beat_bpm=124.0,
                    beat_source="cache",
                    beat_status="ready",
                )
                build_samples_ms.append((time.perf_counter() - build_start) * 1000.0)

                render_start = time.perf_counter()
                output = host.render_frame(frame, context)
                render_samples_ms.append((time.perf_counter() - render_start) * 1000.0)

                if output == "Visualizer throttled":
                    throttled += 1
                else:
                    outputs += 1
                    assert output
                combined_samples_ms.append((time.perf_counter() - frame_start) * 1000.0)

        host_stats = probe.snapshot()
        host.shutdown()

        metrics = {
            "frame_input_build_ms": summarize_samples(build_samples_ms, unit="ms"),
            "host_render_frame_call_ms": summarize_samples(
                render_samples_ms, unit="ms"
            ),
            "frame_build_plus_render_ms": summarize_samples(
                combined_samples_ms, unit="ms"
            ),
        }
        metadata_top = [
            {
                "name": stat.name,
                "count": stat.count,
                "total_ms": round(stat.total_s * 1000.0, 4),
                "max_ms": round(stat.max_s * 1000.0, 4),
                "mean_ms": round(stat.mean_s * 1000.0, 4),
            }
            for stat in host_stats
        ]

        run = PerfRunResult(
            run_id=f"hidden-hotspot-frame-host-{uuid.uuid4().hex[:8]}",
            created_at=utc_now_iso(),
            app_version=None,
            git_sha=None,
            machine={"runner": "pytest-opt-in"},
            config={
                "scenario": "hidden_hotspot_frame_input_and_host_render_overhead",
                "frame_count": 240,
                "plugin_id": "basic",
                "target_fps": 12,
            },
            scenarios=[
                PerfScenarioResult(
                    scenario_id="hidden_hotspot_idle_playback_sweep",
                    category="hidden_hotspot",
                    status="pass",
                    elapsed_s=round(sum(combined_samples_ms) / 1000.0, 6),
                    metrics=metrics,
                    counters={
                        "frame_count": 240,
                        "render_output_frames": outputs,
                        "throttled_frames": throttled,
                        "probed_method_count": len(host_stats),
                    },
                    metadata={
                        "top_cumulative_methods": metadata_top,
                        "visualizer_id": "basic",
                    },
                )
            ],
        )
        return write_perf_run_artifact(run, results_dir=_perf_results_dir(tmp_path))

    artifact_path = run_scenario()
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
                            "visualizer_id": _active_visualizer_id(app),
                        },
                    )
                ],
            )
            artifact_path = write_perf_run_artifact(
                run, results_dir=_perf_results_dir(tmp_path)
            )
            app.exit()
            return artifact_path

    artifact_path = _run(run_scenario())
    assert artifact_path.exists()
