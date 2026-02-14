"""Tests for app-level envelope analysis scheduling."""

from __future__ import annotations

import asyncio
from pathlib import Path

import tz_player.app as app_module
import tz_player.paths as paths
from tz_player.services.audio_envelope_analysis import EnvelopeAnalysisResult
from tz_player.services.player_service import TrackInfo


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
