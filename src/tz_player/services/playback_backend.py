"""Playback backend interface and event types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

BackendStatus = str


@dataclass(frozen=True)
class BackendEvent:
    pass


@dataclass(frozen=True)
class PositionUpdated(BackendEvent):
    position_ms: int
    duration_ms: int


@dataclass(frozen=True)
class StateChanged(BackendEvent):
    status: BackendStatus


@dataclass(frozen=True)
class MediaChanged(BackendEvent):
    duration_ms: int


@dataclass(frozen=True)
class BackendError(BackendEvent):
    message: str


class PlaybackBackend(Protocol):
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
