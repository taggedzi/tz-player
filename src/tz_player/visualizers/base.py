"""Core visualizer plugin interfaces and frame payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class VisualizerContext:
    ansi_enabled: bool
    unicode_enabled: bool


@dataclass(frozen=True)
class VisualizerFrameInput:
    frame_index: int
    monotonic_s: float
    width: int
    height: int
    status: str
    position_s: float
    duration_s: float | None
    volume: float
    speed: float
    repeat_mode: str
    shuffle: bool
    track_id: int | None
    track_path: str | None
    title: str | None
    artist: str | None
    album: str | None
    level_left: float | None = None
    level_right: float | None = None


class VisualizerPlugin(Protocol):
    plugin_id: str
    display_name: str

    def on_activate(self, context: VisualizerContext) -> None: ...
    def on_deactivate(self) -> None: ...
    def render(self, frame: VisualizerFrameInput) -> str: ...
