"""Integration tests for analysis cache persistence across playlist clear."""

from __future__ import annotations

import asyncio
from pathlib import Path

import tz_player.paths as paths
from tz_player.app import TzPlayerApp
from tz_player.services.spectrum_store import SpectrumParams


class _FakeAppDirs:
    def __init__(self, data_dir: Path, config_dir: Path) -> None:
        self.user_data_dir = str(data_dir)
        self.user_config_dir = str(config_dir)


def _run(coro):
    return asyncio.run(coro)


def _setup_dirs(tmp_path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"

    def fake_app_dirs(app_name: str, appauthor: bool | None = None) -> _FakeAppDirs:
        return _FakeAppDirs(data_dir, config_dir)

    monkeypatch.setattr(paths, "AppDirs", fake_app_dirs)
    paths.get_app_dirs.cache_clear()


def test_playlist_clear_does_not_delete_analysis_cache(tmp_path, monkeypatch) -> None:
    _setup_dirs(tmp_path, monkeypatch)
    app = TzPlayerApp(auto_init=False, backend_name="fake")

    track = tmp_path / "song.mp3"
    track.write_bytes(b"abcdef")

    params = SpectrumParams(band_count=4, hop_ms=40)

    async def run_app() -> None:
        async with app.run_test():
            await asyncio.sleep(0)
            await app._initialize_state()
            assert app.audio_envelope_store is not None
            assert app.spectrum_store is not None

            await app.audio_envelope_store.upsert_envelope(
                track,
                [(0, 0.2, 0.3), (100, 0.5, 0.6)],
                duration_ms=100,
            )
            await app.spectrum_store.upsert_spectrum(
                track,
                duration_ms=100,
                params=params,
                frames=[(0, bytes([1, 2, 3, 4]))],
            )

            assert await app.audio_envelope_store.has_envelope(track) is True
            assert await app.spectrum_store.has_spectrum(track, params=params) is True

            await app.handle_playlist_cleared()

            assert await app.audio_envelope_store.has_envelope(track) is True
            assert await app.spectrum_store.has_spectrum(track, params=params) is True
            app.exit()

    _run(run_app())
