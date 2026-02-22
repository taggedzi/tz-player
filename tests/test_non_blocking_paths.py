"""Regression tests for non-blocking IO path contracts."""

from __future__ import annotations

import ast
import asyncio
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from textual.css.query import NoMatches

import tz_player.app as app_module
import tz_player.services.metadata_service as metadata_service_module
import tz_player.ui.playlist_pane as playlist_pane_module
from tz_player.services.audio_analysis_bundle import AnalysisBundleResult
from tz_player.services.audio_beat_analysis import BeatAnalysisResult
from tz_player.services.audio_envelope_analysis import EnvelopeAnalysisResult
from tz_player.services.audio_spectrum_analysis import SpectrumAnalysisResult
from tz_player.services.audio_waveform_proxy_analysis import WaveformProxyAnalysisResult
from tz_player.services.player_service import PlayerState
from tz_player.services.playlist_store import PlaylistRow
from tz_player.ui.playlist_pane import PlaylistPane
from tz_player.utils.async_utils import run_blocking, run_cpu_bound


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


def test_run_cpu_bound_rejects_non_callable() -> None:
    with pytest.raises(TypeError, match="func must be callable"):
        _run(run_cpu_bound(None))  # type: ignore[arg-type]


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


def test_app_analysis_paths_use_run_cpu_bound(monkeypatch, tmp_path) -> None:
    app = app_module.TzPlayerApp(auto_init=False)

    class _SpectrumStore:
        async def has_spectrum(self, _path, *, params):  # type: ignore[no-untyped-def]
            del params
            return False

        async def upsert_spectrum(  # type: ignore[no-untyped-def]
            self, _path, *, duration_ms, params, frames
        ) -> None:
            del duration_ms, params, frames

    class _BeatStore:
        async def has_beats(self, _path, *, params):  # type: ignore[no-untyped-def]
            del params
            return False

        async def upsert_beats(  # type: ignore[no-untyped-def]
            self, _path, *, duration_ms, params, bpm, frames
        ) -> None:
            del duration_ms, params, bpm, frames

    class _WaveformStore:
        async def has_waveform_proxy(  # type: ignore[no-untyped-def]
            self, _path, *, params
        ):
            del params
            return False

        async def upsert_waveform_proxy(  # type: ignore[no-untyped-def]
            self, _path, *, duration_ms, params, frames
        ) -> None:
            del duration_ms, params, frames

    class _EnvelopeStore:
        async def has_envelope(self, _path):  # type: ignore[no-untyped-def]
            return False

        async def upsert_envelope(  # type: ignore[no-untyped-def]
            self, _path, points, *, duration_ms
        ) -> None:
            del points, duration_ms

    app.spectrum_store = _SpectrumStore()  # type: ignore[assignment]
    app.beat_store = _BeatStore()  # type: ignore[assignment]
    app.waveform_proxy_store = _WaveformStore()  # type: ignore[assignment]
    app.audio_envelope_store = _EnvelopeStore()  # type: ignore[assignment]
    app._schedule_analysis_cache_prune = lambda **kwargs: None  # type: ignore[assignment]

    cpu_funcs: list[object] = []

    async def fake_run_cpu_bound(func, /, *args, **kwargs):  # type: ignore[no-untyped-def]
        cpu_funcs.append(func)
        return func(*args, **kwargs)

    async def fail_run_blocking(func, /, *args, **kwargs):  # type: ignore[no-untyped-def]
        if func in {
            app_module.analyze_track_analysis_bundle,
            app_module.analyze_track_envelope,
        }:
            raise AssertionError(
                "analysis path used run_blocking instead of run_cpu_bound"
            )
        return func(*args, **kwargs)

    monkeypatch.setattr(app_module, "run_cpu_bound", fake_run_cpu_bound)
    monkeypatch.setattr(app_module, "run_blocking", fail_run_blocking)
    monkeypatch.setattr(
        app_module,
        "analyze_track_analysis_bundle",
        lambda *_args, **_kwargs: AnalysisBundleResult(
            spectrum=SpectrumAnalysisResult(
                duration_ms=1000,
                frames=[(0, b"\x00")],
            ),
            beat=BeatAnalysisResult(
                duration_ms=1000,
                bpm=120.0,
                frames=[(0, 1, True)],
            ),
            waveform_proxy=WaveformProxyAnalysisResult(
                duration_ms=1000,
                frames=[(0, 0, 0, 0, 0)],
            ),
        ),
    )
    monkeypatch.setattr(
        app_module,
        "analyze_track_envelope",
        lambda *_args, **_kwargs: EnvelopeAnalysisResult(
            duration_ms=1000,
            points=[(0, 0.1, 0.2)],
        ),
    )

    _run(
        app._ensure_spectrum_for_track(
            str(tmp_path / "song.mp3"),
            app_module.SpectrumParams(band_count=8, hop_ms=40),
        )
    )
    _run(
        app._ensure_beat_for_track(
            str(tmp_path / "song.mp3"),
            app_module.BeatParams(hop_ms=40),
        )
    )
    _run(
        app._ensure_waveform_proxy_for_track(
            str(tmp_path / "song.mp3"),
            app_module.WaveformProxyParams(hop_ms=20),
        )
    )
    _run(
        app._ensure_envelope_for_track(
            app_module.TrackInfo(
                title=None,
                artist=None,
                album=None,
                year=None,
                path=str(tmp_path / "song.mp3"),
                duration_ms=None,
            )
        )
    )

    assert app_module.analyze_track_analysis_bundle in cpu_funcs
    assert app_module.analyze_track_envelope in cpu_funcs


def test_spectrum_analysis_schedule_respects_pending_task_cap(tmp_path) -> None:
    app = app_module.TzPlayerApp(auto_init=False)

    class _SpectrumStore:
        pass

    app.spectrum_store = _SpectrumStore()  # type: ignore[assignment]

    async def _run_schedule() -> None:
        sleepers = [
            asyncio.create_task(asyncio.sleep(10))
            for _ in range(app_module.ANALYSIS_MAX_PENDING_TASKS_PER_TYPE)
        ]
        for index, task in enumerate(sleepers):
            app._spectrum_analysis_tasks[f"existing-{index}"] = task
        try:
            await app._schedule_spectrum_analysis_for_path(
                str(tmp_path / "song.mp3"),
                app_module.SpectrumParams(band_count=8, hop_ms=40),
            )
            assert len(app._spectrum_analysis_tasks) == len(sleepers)
        finally:
            for task in sleepers:
                task.cancel()
            await asyncio.gather(*sleepers, return_exceptions=True)

    _run(_run_schedule())


def test_transport_controls_cache_item_indexes() -> None:
    pane = PlaylistPane()

    class _Store:
        def __init__(self) -> None:
            self.calls: list[tuple[int, int]] = []

        async def get_item_index(self, playlist_id: int, item_id: int) -> int:
            self.calls.append((playlist_id, item_id))
            if item_id == 11:
                return 3
            if item_id == 12:
                return 5
            return 1

    store = _Store()
    pane.store = store  # type: ignore[assignment]
    pane.playlist_id = 7
    pane.cursor_item_id = 11
    pane.search_active = False
    pane._last_player_state = PlayerState(
        status="playing",
        playlist_id=7,
        item_id=12,
    )

    _run(pane._refresh_transport_controls())
    _run(pane._refresh_transport_controls())

    assert store.calls == [(7, 11), (7, 12)]


def test_playlist_pane_prefetch_cache_reuses_fetch_window_reads() -> None:
    pane = PlaylistPane()

    class _Store:
        def __init__(self) -> None:
            self.fetch_calls: list[tuple[int, int, int]] = []

        async def count(self, playlist_id: int) -> int:
            del playlist_id
            return 80

        async def fetch_window(
            self, playlist_id: int, offset: int, limit: int
        ) -> list[PlaylistRow]:
            self.fetch_calls.append((playlist_id, offset, limit))
            rows: list[PlaylistRow] = []
            for index in range(offset, offset + limit):
                rows.append(
                    PlaylistRow(
                        item_id=index + 1,
                        track_id=index + 1,
                        pos_key=(index + 1) * 10_000,
                        path=Path(f"/tmp/track-{index + 1}.mp3"),
                        title=None,
                        artist=None,
                        album=None,
                        year=None,
                        duration_ms=None,
                        meta_valid=None,
                        meta_error=None,
                    )
                )
            return rows

    store = _Store()
    pane.store = store  # type: ignore[assignment]
    pane.playlist_id = 1
    pane.limit = 4

    async def _run_case() -> None:
        await pane.refresh_view()
        assert len(store.fetch_calls) == 1

        for offset in range(1, 6):
            pane.window_offset = offset
            await pane._refresh_window()

        assert len(store.fetch_calls) == 1
        pane.window_offset = 14
        await pane._refresh_window()
        assert len(store.fetch_calls) == 2

    _run(_run_case())


def test_visualizer_frame_scheduling_coalesces_pending_ticks() -> None:
    app = app_module.TzPlayerApp(auto_init=False)
    app.visualizer_host = SimpleNamespace(target_fps=10, active_id="basic")
    render_calls: list[str] = []

    async def fake_render() -> None:
        render_calls.append("render")
        await asyncio.sleep(0.02)

    app._render_visualizer_frame_async = fake_render  # type: ignore[assignment]

    async def _run_schedule() -> None:
        app._schedule_visualizer_frame()
        app._schedule_visualizer_frame()
        app._schedule_visualizer_frame()
        await asyncio.sleep(0.08)

    _run(_run_schedule())

    assert len(render_calls) == 2
    assert app._visualizer_render_task is None
    assert app._visualizer_render_pending is False


def test_analysis_schedule_calls_return_without_waiting_for_worker_completion(
    tmp_path,
) -> None:
    app = app_module.TzPlayerApp(auto_init=False)
    app.audio_envelope_store = object()  # type: ignore[assignment]
    app.spectrum_store = object()  # type: ignore[assignment]
    app.beat_store = object()  # type: ignore[assignment]
    app.waveform_proxy_store = object()  # type: ignore[assignment]

    async def slow_envelope(*_args, **_kwargs) -> None:  # type: ignore[no-untyped-def]
        await asyncio.sleep(0.05)

    async def slow_spectrum(*_args, **_kwargs) -> None:  # type: ignore[no-untyped-def]
        await asyncio.sleep(0.05)

    async def slow_beat(*_args, **_kwargs) -> None:  # type: ignore[no-untyped-def]
        await asyncio.sleep(0.05)

    async def slow_wave(*_args, **_kwargs) -> None:  # type: ignore[no-untyped-def]
        await asyncio.sleep(0.05)

    app._ensure_envelope_for_track = slow_envelope  # type: ignore[assignment]
    app._ensure_spectrum_for_track = slow_spectrum  # type: ignore[assignment]
    app._ensure_beat_for_track = slow_beat  # type: ignore[assignment]
    app._ensure_waveform_proxy_for_track = slow_wave  # type: ignore[assignment]

    async def _run_schedule() -> None:
        track = app_module.TrackInfo(
            title=None,
            artist=None,
            album=None,
            year=None,
            path=str(tmp_path / "song.mp3"),
            duration_ms=None,
        )
        await asyncio.wait_for(
            app._schedule_envelope_analysis_for_path(str(tmp_path / "song.mp3")),
            timeout=0.01,
        )
        await asyncio.wait_for(
            app._schedule_spectrum_analysis_for_path(
                str(tmp_path / "song.mp3"),
                app_module.SpectrumParams(band_count=8, hop_ms=40),
            ),
            timeout=0.01,
        )
        await asyncio.wait_for(
            app._schedule_beat_analysis_for_path(
                str(tmp_path / "song.mp3"),
                app_module.BeatParams(hop_ms=40),
            ),
            timeout=0.01,
        )
        await asyncio.wait_for(
            app._schedule_waveform_proxy_analysis_for_path(
                str(tmp_path / "song.mp3"),
                app_module.WaveformProxyParams(hop_ms=20),
            ),
            timeout=0.01,
        )
        app._schedule_envelope_analysis(track)
        await asyncio.sleep(0)
        tasks = [
            *app._envelope_analysis_tasks.values(),
            *app._spectrum_analysis_tasks.values(),
            *app._beat_analysis_tasks.values(),
            *app._waveform_proxy_analysis_tasks.values(),
        ]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    _run(_run_schedule())


def test_visualizer_frame_loop_logs_overrun(caplog) -> None:
    app = app_module.TzPlayerApp(auto_init=False)

    class _SlowHost:
        frame_index = 0
        target_fps = 30
        active_id = "slow.fake"

        def render_frame(self, _frame, _context):  # type: ignore[no-untyped-def]
            time.sleep(0.05)
            return "ok"

        def consume_notice(self):  # type: ignore[no-untyped-def]
            return None

        def shutdown(self) -> None:
            return None

    async def _run_app() -> None:
        async with app.run_test():
            app.visualizer_host = _SlowHost()  # type: ignore[assignment]
            with caplog.at_level("INFO"):
                await app._render_visualizer_frame_async()
            app.exit()

    _run(_run_app())
    assert any(
        getattr(record, "event", None) == "visualizer_frame_loop_overrun"
        for record in caplog.records
    )


def test_visualizer_runtime_fps_backs_off_after_sustained_overruns(monkeypatch) -> None:
    app = app_module.TzPlayerApp(auto_init=False)
    app.state = replace(app.state, visualizer_fps=22)
    app.visualizer_host = SimpleNamespace(active_id="slow.fake", target_fps=22)
    app._visualizer_runtime_fps = 22

    applied: list[int] = []

    def _apply(fps: int) -> None:
        applied.append(fps)
        app._visualizer_runtime_fps = fps

    monkeypatch.setattr(app, "_apply_visualizer_timer_fps", _apply)

    for _ in range(app_module.VISUALIZER_OVERRUN_STREAK_FOR_BACKOFF):
        app._adapt_visualizer_runtime_fps(elapsed_s=0.20)

    assert applied
    assert applied[-1] == 18


def test_visualizer_runtime_fps_backs_off_from_accumulated_overrun_score(
    monkeypatch,
) -> None:
    app = app_module.TzPlayerApp(auto_init=False)
    app.state = replace(app.state, visualizer_fps=22)
    app.visualizer_host = SimpleNamespace(active_id="spiky.fake", target_fps=22)
    app._visualizer_runtime_fps = 22

    applied: list[int] = []

    def _apply(fps: int) -> None:
        applied.append(fps)
        app._visualizer_runtime_fps = fps

    monkeypatch.setattr(app, "_apply_visualizer_timer_fps", _apply)

    # Intermittent heavy overruns with healthy frames between should still back off.
    app._adapt_visualizer_runtime_fps(elapsed_s=0.09)
    app._adapt_visualizer_runtime_fps(elapsed_s=0.01)
    app._adapt_visualizer_runtime_fps(elapsed_s=0.09)
    app._adapt_visualizer_runtime_fps(elapsed_s=0.01)
    app._adapt_visualizer_runtime_fps(elapsed_s=0.09)

    assert applied
    assert applied[-1] == 20


def test_visualizer_runtime_fps_recovers_after_stable_frames(monkeypatch) -> None:
    app = app_module.TzPlayerApp(auto_init=False)
    app.state = replace(app.state, visualizer_fps=12)
    app.visualizer_host = SimpleNamespace(active_id="stable.fake", target_fps=12)
    app._visualizer_runtime_fps = 10

    applied: list[int] = []

    def _apply(fps: int) -> None:
        applied.append(fps)
        app._visualizer_runtime_fps = fps

    monkeypatch.setattr(app, "_apply_visualizer_timer_fps", _apply)

    for _ in range(app_module.VISUALIZER_HEALTHY_FRAMES_FOR_RECOVERY):
        app._adapt_visualizer_runtime_fps(elapsed_s=0.01)

    assert applied
    assert applied[-1] == 11


def test_handle_player_event_ignores_updates_when_playlist_pane_missing() -> None:
    app = app_module.TzPlayerApp(auto_init=False)

    def _raise_no_matches(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise NoMatches("pane missing")

    app.query_one = _raise_no_matches  # type: ignore[assignment]
    event = app_module.PlayerStateChanged(PlayerState(status="playing", item_id=1))
    _run(app._handle_player_event(event))


def test_playlist_limit_is_capped_for_tall_viewports() -> None:
    pane = PlaylistPane()
    pane._viewport = SimpleNamespace(size=SimpleNamespace(height=220))  # type: ignore[assignment]
    _run(pane._recompute_limit())
    assert pane.limit == playlist_pane_module.PLAYLIST_WINDOW_MAX_ROWS


def test_cycle_visualizer_keeps_runtime_fps_budget(monkeypatch) -> None:
    app = app_module.TzPlayerApp(auto_init=False)
    app.state = replace(app.state, visualizer_id="viz.a", visualizer_fps=22)
    app._visualizer_runtime_fps = 10

    class _Registry:
        def plugin_ids(self) -> list[str]:
            return ["viz.a", "viz.b"]

    class _Host:
        active_id = "viz.a"

        def activate(self, plugin_id: str, _context):  # type: ignore[no-untyped-def]
            self.active_id = plugin_id
            return plugin_id

    scheduled: list[bool] = []

    async def _save(_state):  # type: ignore[no-untyped-def]
        return None

    app.visualizer_registry = _Registry()  # type: ignore[assignment]
    app.visualizer_host = _Host()  # type: ignore[assignment]
    app._save_state_snapshot = _save  # type: ignore[assignment]
    app._schedule_visualizer_frame = lambda: scheduled.append(True)  # type: ignore[assignment]

    _run(app.action_cycle_visualizer())

    assert app.state.visualizer_id == "viz.b"
    assert app._visualizer_runtime_fps == 10
    assert scheduled


def test_spectrum_schedule_coalesces_rapid_requeue_with_cooldown(tmp_path) -> None:
    app = app_module.TzPlayerApp(auto_init=False)
    app.spectrum_store = object()  # type: ignore[assignment]
    calls = {"count": 0}

    async def fast_ensure(*_args, **_kwargs) -> None:  # type: ignore[no-untyped-def]
        calls["count"] += 1
        await asyncio.sleep(0)

    app._ensure_spectrum_for_track = fast_ensure  # type: ignore[assignment]

    async def _run_schedule() -> None:
        await app._schedule_spectrum_analysis_for_path(
            str(tmp_path / "song.mp3"),
            app_module.SpectrumParams(band_count=8, hop_ms=40),
        )
        await asyncio.sleep(0.01)
        await app._schedule_spectrum_analysis_for_path(
            str(tmp_path / "song.mp3"),
            app_module.SpectrumParams(band_count=8, hop_ms=40),
        )
        await asyncio.sleep(0.05)
        tasks = list(app._spectrum_analysis_tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    _run(_run_schedule())
    assert calls["count"] == 1


def test_cancel_stale_analysis_tasks_keeps_only_active_track_path() -> None:
    app = app_module.TzPlayerApp(auto_init=False)

    async def _run_cancel() -> None:
        old_envelope = asyncio.create_task(asyncio.sleep(10))
        keep_envelope = asyncio.create_task(asyncio.sleep(10))
        old_spectrum = asyncio.create_task(asyncio.sleep(10))
        keep_spectrum = asyncio.create_task(asyncio.sleep(10))

        app._envelope_analysis_tasks["/old.mp3"] = old_envelope
        app._envelope_analysis_tasks["/keep.mp3"] = keep_envelope
        app._spectrum_analysis_tasks["/old.mp3|bands=8|hop=40"] = old_spectrum
        app._spectrum_analysis_tasks["/keep.mp3|bands=8|hop=40"] = keep_spectrum

        app._envelope_analysis_last_scheduled["/old.mp3"] = 1.0
        app._envelope_analysis_last_scheduled["/keep.mp3"] = 1.0
        app._spectrum_analysis_last_scheduled["/old.mp3|bands=8|hop=40"] = 1.0
        app._spectrum_analysis_last_scheduled["/keep.mp3|bands=8|hop=40"] = 1.0

        app._cancel_stale_analysis_tasks(active_paths={"/keep.mp3"})
        await asyncio.sleep(0)

        assert "/old.mp3" not in app._envelope_analysis_tasks
        assert "/old.mp3|bands=8|hop=40" not in app._spectrum_analysis_tasks
        assert "/old.mp3" not in app._envelope_analysis_last_scheduled
        assert "/old.mp3|bands=8|hop=40" not in app._spectrum_analysis_last_scheduled

        assert "/keep.mp3" in app._envelope_analysis_tasks
        assert "/keep.mp3|bands=8|hop=40" in app._spectrum_analysis_tasks

        keep_envelope.cancel()
        keep_spectrum.cancel()
        await asyncio.gather(keep_envelope, keep_spectrum, return_exceptions=True)

    _run(_run_cancel())
