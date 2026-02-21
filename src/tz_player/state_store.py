"""JSON persistence for user-facing app runtime state.

The store is intentionally tolerant of invalid/missing values so upgrades and
partial/corrupt writes degrade to safe defaults instead of aborting startup.
"""

from __future__ import annotations

import json
import logging
import math
import time
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AppState:
    """Persisted application state loaded at startup and updated during runtime."""

    playlist_id: int | None = None
    current_item_id: int | None = None
    volume: float = 1.0
    speed: float = 1.0
    repeat_mode: str = "off"
    shuffle: bool = False
    playback_backend: str = "vlc"
    visualizer_id: str | None = None
    visualizer_fps: int = 10
    visualizer_responsiveness_profile: str = "balanced"
    visualizer_plugin_paths: tuple[str, ...] = ()
    visualizer_plugin_security_mode: str = "warn"
    visualizer_plugin_runtime_mode: str = "in-process"
    ansi_enabled: bool = True
    log_level: str = "INFO"


def _coerce_state(data: dict[str, Any]) -> AppState:
    """Coerce untyped JSON object into validated `AppState` with safe defaults.

    This doubles as lightweight schema evolution handling for older keys
    (for example `current_track_id` -> `current_item_id`).
    """

    def _int_or_none(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        return int(value) if isinstance(value, int) else None

    def _float_or_default(value: Any, default: float) -> float:
        if isinstance(value, bool):
            return default
        if isinstance(value, (int, float)):
            normalized = float(value)
            if math.isfinite(normalized):
                return normalized
            return default
        return default

    def _bool_or_default(value: Any, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        return default

    def _str_or_default(value: Any, default: str) -> str:
        if isinstance(value, str):
            return value
        return default

    def _int_or_default(value: Any, default: int) -> int:
        if isinstance(value, bool):
            return default
        if isinstance(value, int):
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
        playback_backend=_str_or_default(data.get("playback_backend"), "vlc"),
        visualizer_id=data.get("visualizer_id")
        if isinstance(data.get("visualizer_id"), str)
        else None,
        visualizer_fps=_int_or_default(data.get("visualizer_fps"), 10),
        visualizer_responsiveness_profile=_str_or_default(
            data.get("visualizer_responsiveness_profile"), "balanced"
        ),
        visualizer_plugin_paths=tuple(
            value
            for value in data.get("visualizer_plugin_paths", [])
            if isinstance(value, str) and value.strip()
        )
        if isinstance(data.get("visualizer_plugin_paths"), list)
        else (),
        visualizer_plugin_security_mode=_str_or_default(
            data.get("visualizer_plugin_security_mode"), "warn"
        ),
        visualizer_plugin_runtime_mode=_str_or_default(
            data.get("visualizer_plugin_runtime_mode"), "in-process"
        ),
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
    """Persist state atomically to disk via write-then-replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
    payload = json.dumps(asdict(state), indent=2, sort_keys=True)
    delay_s = 0.02
    try:
        for attempt in range(4):
            tmp_path.write_text(payload, encoding="utf-8")
            try:
                tmp_path.replace(path)
                return
            except OSError as exc:
                if not _is_retryable_windows_replace_error(exc) or attempt >= 3:
                    raise
                time.sleep(delay_s)
                delay_s = min(0.25, delay_s * 2.0)
    finally:
        with suppress(OSError):
            tmp_path.unlink()


def _is_retryable_windows_replace_error(exc: OSError) -> bool:
    """Return whether an atomic replace failure is likely transient on Windows."""
    winerror = getattr(exc, "winerror", None)
    if winerror in {32, 5, 2}:
        return True
    errno = getattr(exc, "errno", None)
    if errno in {13, 16}:
        return True
    text = str(exc).lower()
    return "used by another process" in text or "permission denied" in text
