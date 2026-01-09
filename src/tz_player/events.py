"""Event models for player state updates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tz_player.services.player_service import PlayerState, TrackInfo


@dataclass(frozen=True)
class PlayerStateChanged:
    state: PlayerState


@dataclass(frozen=True)
class TrackChanged:
    track_info: TrackInfo | None
