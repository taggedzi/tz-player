"""Playback backend contracts and event payloads.

`PlayerService` depends on this protocol to stay backend-agnostic. Concrete
implementations (fake/VLC) translate engine-specific behavior into these shared
commands and events.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

BackendStatus = Literal["idle", "loading", "playing", "paused", "stopped", "error"]


@dataclass(frozen=True)
class BackendEvent:
    """Marker base type for backend-originated events."""

    pass


@dataclass(frozen=True)
class PositionUpdated(BackendEvent):
    """Periodic transport position update in milliseconds."""

    position_ms: int
    duration_ms: int


@dataclass(frozen=True)
class StateChanged(BackendEvent):
    """Backend playback state transition."""

    status: BackendStatus


@dataclass(frozen=True)
class MediaChanged(BackendEvent):
    """Loaded media metadata update (currently duration only)."""

    duration_ms: int


@dataclass(frozen=True)
class BackendError(BackendEvent):
    """Backend-reported non-recoverable runtime error."""

    message: str


@dataclass(frozen=True)
class LevelSample:
    """Stereo audio-level sample normalized to [0.0, 1.0]."""

    left: float
    right: float


@runtime_checkable
class PlaybackLevelProvider(Protocol):
    """Optional capability protocol for live audio level sampling."""

    async def get_level_sample(self) -> LevelSample | None: ...


class PlaybackBackend(Protocol):
    """Playback engine protocol consumed by `PlayerService`."""

    def set_event_handler(
        self, handler: Callable[[BackendEvent], Awaitable[None]]
    ) -> None: ...

    async def start(self) -> None: ...

    async def shutdown(self) -> None: ...

    async def play(
        self,
        item_id: int,
        track_path: str,
        start_ms: int = 0,
        *,
        duration_ms: int | None = None,
    ) -> None: ...

    async def toggle_pause(self) -> None: ...

    async def stop(self) -> None: ...

    async def seek_ms(self, position_ms: int) -> None: ...

    async def set_volume(self, volume: int) -> None: ...

    async def set_speed(self, speed: float) -> None: ...

    async def get_position_ms(self) -> int: ...

    async def get_duration_ms(self) -> int: ...

    async def get_state(self) -> BackendStatus: ...
