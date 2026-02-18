"""Tests for platform-specific paths."""

from __future__ import annotations

from pathlib import Path

import tz_player.paths as paths


class FakeAppDirs:
    """Minimal AppDirs stand-in used to control path roots during tests."""

    def __init__(self, data_dir: Path, config_dir: Path) -> None:
        self.user_data_dir = str(data_dir)
        self.user_config_dir = str(config_dir)


def test_paths_use_platformdirs_and_create_dirs(tmp_path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"

    def fake_app_dirs(app_name: str, appauthor: bool | None = None) -> FakeAppDirs:
        assert appauthor is False
        return FakeAppDirs(data_dir, config_dir)

    monkeypatch.setattr(paths, "AppDirs", fake_app_dirs)
    paths.get_app_dirs.cache_clear()

    assert paths.data_dir() == data_dir
    assert paths.config_dir() == config_dir
    assert paths.log_dir() == data_dir / "logs"
    assert paths.db_path() == data_dir / "tz-player.sqlite"
    assert paths.state_path() == config_dir / "state.json"

    assert data_dir.exists()
    assert config_dir.exists()
    assert (data_dir / "logs").exists()
