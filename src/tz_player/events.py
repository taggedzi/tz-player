"""Cross-module event/message models for service and UI communication.

Dataclass events are used for app/service signaling, while `textual.message`
types are used for widget-level interaction routing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from textual.message import Message

if TYPE_CHECKING:
    from tz_player.services.player_service import PlayerState, TrackInfo


@dataclass(frozen=True)
class PlayerStateChanged:
    """Service event emitted when the effective player state changes."""

    state: PlayerState


@dataclass(frozen=True)
class TrackChanged:
    """Service event emitted when current track metadata context changes."""

    track_info: TrackInfo | None


class PlaylistRowClicked(Message):
    """UI message for single-click selection of a playlist row item."""

    def __init__(self, item_id: int) -> None:
        super().__init__()
        self.item_id = item_id


class PlaylistRowDoubleClicked(Message):
    """UI message for double-click activation (play) of a playlist row item."""

    def __init__(self, item_id: int) -> None:
        super().__init__()
        self.item_id = item_id


class PlaylistScrollRequested(Message):
    """UI message requesting relative viewport scroll movement."""

    def __init__(self, delta: int) -> None:
        super().__init__()
        self.delta = delta


class PlaylistJumpRequested(Message):
    """UI message requesting absolute viewport jump to an offset."""

    def __init__(self, offset: int) -> None:
        super().__init__()
        self.offset = offset
