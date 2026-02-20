"""Core visualizer plugin contracts and frame/context payloads.

These dataclasses/protocols define the host-plugin boundary used by built-in and
user-discovered visualizers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class VisualizerContext:
    """Runtime rendering context shared across plugin activation/render calls."""

    ansi_enabled: bool
    unicode_enabled: bool


@dataclass(frozen=True)
class VisualizerFrameInput:
    """Per-frame playback snapshot supplied to visualizer render functions."""

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
    level_source: str | None = None
    level_status: str | None = None
    spectrum_bands: bytes | None = None
    spectrum_source: str | None = None
    spectrum_status: str | None = None
    waveform_min_left: float | None = None
    waveform_max_left: float | None = None
    waveform_min_right: float | None = None
    waveform_max_right: float | None = None
    waveform_source: str | None = None
    waveform_status: str | None = None
    beat_strength: float | None = None
    beat_is_onset: bool | None = None
    beat_bpm: float | None = None
    beat_source: str | None = None
    beat_status: str | None = None


class VisualizerPlugin(Protocol):
    """Protocol each visualizer plugin implementation must satisfy."""

    plugin_id: str
    display_name: str
    plugin_api_version: int

    def on_activate(self, context: VisualizerContext) -> None: ...
    def on_deactivate(self) -> None: ...
    def render(self, frame: VisualizerFrameInput) -> str: ...
