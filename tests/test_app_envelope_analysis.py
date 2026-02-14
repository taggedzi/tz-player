"""Tests for app-level envelope analysis scheduling."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import tz_player.app as app_module
import tz_player.paths as paths
from tz_player.services.audio_envelope_analysis import EnvelopeAnalysisResult
from tz_player.services.player_service import PlayerState, TrackInfo


def _run(coro):
    return asyncio.run(coro)


class _StoreStub:
    def __init__(self, *, has_hit: bool) -> None:
        self.has_hit = has_hit
        self.upserts: list[tuple[str, int, int]] = []

    async def has_envelope(self, track_path):  # type: ignore[no-untyped-def]
        del track_path
        return self.has_hit

    async def upsert_envelope(  # type: ignore[no-untyped-def]
        self, track_path, points, *, duration_ms
    ) -> None:
        self.upserts.append((str(track_path), len(points), duration_ms))


def _track() -> TrackInfo:
    return TrackInfo(
        title="Song",
        artist="Artist",
        album="Album",
        year=2020,
        path="/tmp/song.mp3",
        duration_ms=12_345,
    )


class _FakeAppDirs:
    def __init__(self, data_dir: Path, config_dir: Path) -> None:
        self.user_data_dir = str(data_dir)
        self.user_config_dir = str(config_dir)


def _setup_dirs(tmp_path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"

    def fake_app_dirs(app_name: str, appauthor: bool | None = None) -> _FakeAppDirs:
        return _FakeAppDirs(data_dir, config_dir)

    monkeypatch.setattr(paths, "AppDirs", fake_app_dirs)
    paths.get_app_dirs.cache_clear()


def test_ensure_envelope_for_track_skips_when_cache_hit(tmp_path, monkeypatch) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    app = app_module.TzPlayerApp(auto_init=False)
    store = _StoreStub(has_hit=True)
    app.audio_envelope_store = store  # type: ignore[assignment]

    called = {"count": 0}

    def _analyze(_path):  # type: ignore[no-untyped-def]
        called["count"] += 1
        return EnvelopeAnalysisResult(duration_ms=1000, points=[(0, 0.1, 0.1)])

    monkeypatch.setattr(app_module, "analyze_track_envelope", _analyze)
    _run(app._ensure_envelope_for_track(_track()))

    assert called["count"] == 0
    assert store.upserts == []


def test_ensure_envelope_for_track_upserts_when_analysis_available(
    tmp_path,
    monkeypatch,
) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    app = app_module.TzPlayerApp(auto_init=False)
    store = _StoreStub(has_hit=False)
    app.audio_envelope_store = store  # type: ignore[assignment]

    def _analyze(_path):  # type: ignore[no-untyped-def]
        return EnvelopeAnalysisResult(
            duration_ms=1200,
            points=[
                (0, 0.1, 0.2),
                (500, 0.4, 0.5),
            ],
        )

    monkeypatch.setattr(app_module, "analyze_track_envelope", _analyze)
    _run(app._ensure_envelope_for_track(_track()))

    assert store.upserts == [("/tmp/song.mp3", 2, 1200)]


def test_missing_ffmpeg_sets_notice_and_warns_once(
    tmp_path, monkeypatch, caplog
) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    app = app_module.TzPlayerApp(auto_init=False)
    store = _StoreStub(has_hit=False)
    app.audio_envelope_store = store  # type: ignore[assignment]
    app.current_track = _track()

    monkeypatch.setattr(app_module, "analyze_track_envelope", lambda _path: None)
    monkeypatch.setattr(app_module, "ffmpeg_available", lambda: False)
    monkeypatch.setattr(app_module, "requires_ffmpeg_for_envelope", lambda _path: True)

    with caplog.at_level("WARNING"):
        _run(app._ensure_envelope_for_track(_track()))
        _run(app._ensure_envelope_for_track(_track()))

    assert app._audio_level_notice is not None
    assert "ffmpeg missing" in app._audio_level_notice.lower()
    warnings = [
        rec.message for rec in caplog.records if "ffmpeg not found" in rec.message
    ]
    assert len(warnings) == 1


def test_wav_path_without_ffmpeg_keeps_notice_clear(tmp_path, monkeypatch) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    app = app_module.TzPlayerApp(auto_init=False)
    store = _StoreStub(has_hit=False)
    app.audio_envelope_store = store  # type: ignore[assignment]
    app.current_track = TrackInfo(
        title="Tone",
        artist="A",
        album="B",
        year=2020,
        path="/tmp/tone.wav",
        duration_ms=1000,
    )

    monkeypatch.setattr(app_module, "analyze_track_envelope", lambda _path: None)
    monkeypatch.setattr(app_module, "ffmpeg_available", lambda: False)
    monkeypatch.setattr(app_module, "requires_ffmpeg_for_envelope", lambda _path: False)

    _run(app._ensure_envelope_for_track(app.current_track))
    assert app._audio_level_notice is None


def test_next_track_prewarm_schedules_and_warms_predicted_item(
    tmp_path, monkeypatch
) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    app = app_module.TzPlayerApp(auto_init=False)
    app.audio_envelope_store = _StoreStub(has_hit=False)  # type: ignore[assignment]
    app.player_state = PlayerState(
        status="playing",
        playlist_id=1,
        item_id=1,
        position_ms=1234,
        repeat_mode="ALL",
        shuffle=False,
    )

    class _PredictStub:
        async def predict_next_item_id(self) -> int | None:
            return 2

    class _StoreWithRow:
        async def get_item_row(self, _playlist_id: int, _item_id: int):  # type: ignore[no-untyped-def]
            return SimpleNamespace(
                title="Next Song",
                artist=None,
                album=None,
                year=None,
                path=Path("/tmp/next.mp3"),
                duration_ms=1000,
            )

    warmed: list[str] = []

    async def _capture(track: TrackInfo) -> None:
        warmed.append(track.path)

    app.player_service = _PredictStub()  # type: ignore[assignment]
    app.store = _StoreWithRow()  # type: ignore[assignment]
    monkeypatch.setattr(app, "_ensure_envelope_for_track", _capture)

    async def run() -> None:
        app._schedule_next_track_prewarm()
        await asyncio.sleep(0.25)

    _run(run())
    assert warmed == ["/tmp/next.mp3"]


def test_next_track_prewarm_cancels_when_not_playing(tmp_path, monkeypatch) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    app = app_module.TzPlayerApp(auto_init=False)
    app.audio_envelope_store = _StoreStub(has_hit=False)  # type: ignore[assignment]
    app.player_state = PlayerState(status="stopped", playlist_id=1, item_id=1)

    class _PredictStub:
        async def predict_next_item_id(self) -> int | None:
            return 2

    app.player_service = _PredictStub()  # type: ignore[assignment]
    app._schedule_next_track_prewarm()
    assert app._next_prewarm_task is None


def test_next_track_prewarm_does_not_repeat_same_context(tmp_path, monkeypatch) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    app = app_module.TzPlayerApp(auto_init=False)
    app.audio_envelope_store = _StoreStub(has_hit=False)  # type: ignore[assignment]
    app.player_state = PlayerState(
        status="playing",
        playlist_id=1,
        item_id=1,
        position_ms=1234,
        repeat_mode="ALL",
        shuffle=False,
    )

    class _PredictStub:
        async def predict_next_item_id(self) -> int | None:
            return 2

    class _StoreWithRow:
        async def get_item_row(self, _playlist_id: int, _item_id: int):  # type: ignore[no-untyped-def]
            return SimpleNamespace(
                title="Next Song",
                artist=None,
                album=None,
                year=None,
                path=Path("/tmp/next.mp3"),
                duration_ms=1000,
            )

    warmed: list[str] = []

    async def _capture(track: TrackInfo) -> None:
        warmed.append(track.path)

    app.player_service = _PredictStub()  # type: ignore[assignment]
    app.store = _StoreWithRow()  # type: ignore[assignment]
    monkeypatch.setattr(app, "_ensure_envelope_for_track", _capture)

    async def run() -> None:
        app._schedule_next_track_prewarm()
        await asyncio.sleep(0.25)
        # Same context should not schedule another prewarm.
        app._schedule_next_track_prewarm()
        await asyncio.sleep(0.25)

    _run(run())
    assert warmed == ["/tmp/next.mp3"]
