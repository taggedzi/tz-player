"""Path helpers for per-user app data."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from platformdirs import AppDirs

DEFAULT_APP_NAME = "tz-player"


@lru_cache(maxsize=4)
def get_app_dirs(app_name: str = DEFAULT_APP_NAME) -> AppDirs:
    """Return platform-specific app directories."""
    return AppDirs(app_name)


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_dir(app_name: str = DEFAULT_APP_NAME) -> Path:
    """Return the per-user data directory, creating it if needed."""
    return _ensure_dir(Path(get_app_dirs(app_name).user_data_dir))


def config_dir(app_name: str = DEFAULT_APP_NAME) -> Path:
    """Return the per-user config directory, creating it if needed."""
    return _ensure_dir(Path(get_app_dirs(app_name).user_config_dir))


def log_dir(app_name: str = DEFAULT_APP_NAME) -> Path:
    """Return the per-user log directory, creating it if needed."""
    return _ensure_dir(data_dir(app_name) / "logs")


def db_path(app_name: str = DEFAULT_APP_NAME) -> Path:
    """Return the SQLite database path."""
    return data_dir(app_name) / "tz-player.sqlite"


def state_path(app_name: str = DEFAULT_APP_NAME) -> Path:
    """Return the JSON state file path."""
    return config_dir(app_name) / "state.json"
