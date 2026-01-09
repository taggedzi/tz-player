"""Event models for player state updates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from textual.message import Message

if TYPE_CHECKING:
    from tz_player.services.player_service import PlayerState, TrackInfo


@dataclass(frozen=True)
class PlayerStateChanged:
    state: PlayerState


@dataclass(frozen=True)
class TrackChanged:
    track_info: TrackInfo | None


class PlaylistRowClicked(Message):
    def __init__(self, item_id: int) -> None:
        super().__init__()
        self.item_id = item_id


class PlaylistRowDoubleClicked(Message):
    def __init__(self, item_id: int) -> None:
        super().__init__()
        self.item_id = item_id


class PlaylistScrollRequested(Message):
    def __init__(self, delta: int) -> None:
        super().__init__()
        self.delta = delta


class PlaylistJumpRequested(Message):
    def __init__(self, offset: int) -> None:
        super().__init__()
        self.offset = offset
