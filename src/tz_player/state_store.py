"""Persistent state storage."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AppState:
    playlist_id: int | None = None
    current_item_id: int | None = None
    volume: float = 1.0
    speed: float = 1.0
    repeat_mode: str = "off"
    shuffle: bool = False
    playback_backend: str = "fake"
    visualizer_id: str | None = None
    ansi_enabled: bool = True
    log_level: str = "INFO"


def _coerce_state(data: dict[str, Any]) -> AppState:
    def _int_or_none(value: Any) -> int | None:
        return int(value) if isinstance(value, int) else None

    def _float_or_default(value: Any, default: float) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        return default

    def _bool_or_default(value: Any, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        return default

    def _str_or_default(value: Any, default: str) -> str:
        if isinstance(value, str):
            return value
        return default

    return AppState(
        playlist_id=_int_or_none(data.get("playlist_id")),
        current_item_id=_int_or_none(data.get("current_item_id"))
        if "current_item_id" in data
        else _int_or_none(data.get("current_track_id")),
        volume=_float_or_default(data.get("volume"), 1.0),
        speed=_float_or_default(data.get("speed"), 1.0),
        repeat_mode=_str_or_default(data.get("repeat_mode"), "off"),
        shuffle=_bool_or_default(data.get("shuffle"), False),
        playback_backend=_str_or_default(data.get("playback_backend"), "fake"),
        visualizer_id=data.get("visualizer_id")
        if isinstance(data.get("visualizer_id"), str)
        else None,
        ansi_enabled=_bool_or_default(data.get("ansi_enabled"), True),
        log_level=_str_or_default(data.get("log_level"), "INFO"),
    )


def load_state_with_notice(path: Path) -> tuple[AppState, str | None]:
    """Load state and return an optional user-facing notice."""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("State file missing at %s; using defaults.", path)
        return AppState(), None
    except OSError as exc:
        logger.warning("Failed to read state file %s: %s; using defaults.", path, exc)
        return (
            AppState(),
            "State settings were reset to defaults.\n"
            "Likely cause: state file is unreadable due to permissions or IO issues.\n"
            f"Next step: verify access to '{path}' and restart.",
        )

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("State file at %s is invalid JSON; using defaults.", path)
        return (
            AppState(),
            "State settings were reset to defaults.\n"
            "Likely cause: state file is corrupt or partially written.\n"
            f"Next step: remove or repair '{path}' and restart.",
        )

    if not isinstance(data, dict):
        logger.warning("State file at %s is not a JSON object; using defaults.", path)
        return (
            AppState(),
            "State settings were reset to defaults.\n"
            "Likely cause: state file format is invalid for this app version.\n"
            f"Next step: remove '{path}' and restart.",
        )

    return _coerce_state(data), None


def load_state(path: Path) -> AppState:
    """Load the application state from disk, falling back to defaults."""
    state, _notice = load_state_with_notice(path)
    return state


def save_state(path: Path, state: AppState) -> None:
    """Persist state atomically to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(asdict(state), indent=2, sort_keys=True)
    tmp_path.write_text(payload, encoding="utf-8")
    tmp_path.replace(path)
