"""Tests for app-level beat analysis selection and fallback behavior."""

from __future__ import annotations

import asyncio
from pathlib import Path

import tz_player.app as app_module
import tz_player.paths as paths
from tz_player.services.audio_beat_analysis import BeatAnalysisResult
from tz_player.services.beat_store import BeatParams


class _FakeAppDirs:
    def __init__(self, data_dir: Path, config_dir: Path) -> None:
        self.user_data_dir = str(data_dir)
        self.user_config_dir = str(config_dir)


def _setup_dirs(tmp_path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"

    def fake_app_dirs(app_name: str, appauthor: bool | None = None) -> _FakeAppDirs:
        del app_name, appauthor
        return _FakeAppDirs(data_dir, config_dir)

    monkeypatch.setattr(paths, "AppDirs", fake_app_dirs)
    paths.get_app_dirs.cache_clear()


def _run(coro):
    return asyncio.run(coro)


class _BeatStoreStub:
    def __init__(self) -> None:
        self.upserts: list[tuple[str, BeatParams, float, int]] = []

    async def has_beats(self, path, *, params):  # type: ignore[no-untyped-def]
        del path, params
        return False

    async def upsert_beats(  # type: ignore[no-untyped-def]
        self, path, *, duration_ms, params, bpm, frames
    ) -> None:
        self.upserts.append((str(path), params, bpm, len(frames)))


def test_ensure_beat_for_track_uses_requested_analyzer(tmp_path, monkeypatch) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    app = app_module.TzPlayerApp(auto_init=False)
    app.beat_store = _BeatStoreStub()  # type: ignore[assignment]

    track = tmp_path / "song.mp3"
    track.write_bytes(b"abc")
    called: list[str] = []

    def _native(*args, **kwargs):  # type: ignore[no-untyped-def]
        called.append("native")
        return BeatAnalysisResult(duration_ms=1000, bpm=110.0, frames=[(0, 20, False)])

    def _librosa(*args, **kwargs):  # type: ignore[no-untyped-def]
        called.append("librosa")
        return BeatAnalysisResult(duration_ms=1000, bpm=112.0, frames=[(0, 200, True)])

    async def _run_blocking(func, *args, **kwargs):  # type: ignore[no-untyped-def]
        return func(*args, **kwargs)

    monkeypatch.setattr(app_module, "analyze_track_beats", _native)
    monkeypatch.setattr(app_module, "analyze_track_beats_librosa", _librosa)
    monkeypatch.setattr(app_module, "run_blocking", _run_blocking)

    _run(
        app._ensure_beat_for_track(
            str(track), BeatParams(hop_ms=40, analyzer="librosa")
        )
    )
    assert called == ["librosa"]
    assert app.beat_store.upserts  # type: ignore[union-attr]
    assert app.beat_store.upserts[0][2] == 112.0  # type: ignore[union-attr]


def test_ensure_beat_for_track_falls_back_to_native_when_librosa_empty(
    tmp_path, monkeypatch
) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    app = app_module.TzPlayerApp(auto_init=False)
    app.beat_store = _BeatStoreStub()  # type: ignore[assignment]

    track = tmp_path / "song.mp3"
    track.write_bytes(b"abc")
    called: list[str] = []

    def _native(*args, **kwargs):  # type: ignore[no-untyped-def]
        called.append("native")
        return BeatAnalysisResult(duration_ms=1000, bpm=108.0, frames=[(0, 180, True)])

    def _librosa(*args, **kwargs):  # type: ignore[no-untyped-def]
        called.append("librosa")
        return None

    async def _run_blocking(func, *args, **kwargs):  # type: ignore[no-untyped-def]
        return func(*args, **kwargs)

    monkeypatch.setattr(app_module, "analyze_track_beats", _native)
    monkeypatch.setattr(app_module, "analyze_track_beats_librosa", _librosa)
    monkeypatch.setattr(app_module, "run_blocking", _run_blocking)
    monkeypatch.setattr(app_module, "librosa_available", lambda: True)

    _run(
        app._ensure_beat_for_track(
            str(track), BeatParams(hop_ms=40, analyzer="librosa")
        )
    )
    assert called == ["librosa", "native"]
    assert app.beat_store.upserts  # type: ignore[union-attr]
    assert app.beat_store.upserts[0][2] == 108.0  # type: ignore[union-attr]
