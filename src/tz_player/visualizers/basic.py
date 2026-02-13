"""Basic built-in visualizer."""

from __future__ import annotations

from dataclasses import dataclass

from .base import VisualizerContext, VisualizerFrameInput


@dataclass
class BasicVisualizer:
    plugin_id: str = "basic"
    display_name: str = "Basic"
    _ansi_enabled: bool = True

    def on_activate(self, context: VisualizerContext) -> None:
        self._ansi_enabled = context.ansi_enabled

    def on_deactivate(self) -> None:
        return None

    def render(self, frame: VisualizerFrameInput) -> str:
        width = max(1, frame.width)
        if frame.status not in {"playing", "paused"}:
            return "Idle" if frame.status in {"idle", "stopped"} else "Loading"

        if frame.status == "paused":
            return "Paused"

        bar_width = max(8, min(width, 40))
        pct = 0.0
        if frame.duration_s is not None and frame.duration_s > 0:
            pct = min(max(frame.position_s / frame.duration_s, 0.0), 1.0)
        fill = int(round(bar_width * pct))
        bar = ("#" * fill).ljust(bar_width, "-")
        title = frame.title or (frame.track_path or "")
        title = title.split("/")[-1].split("\\")[-1] if title else "Unknown track"
        return f"[{bar}] {int(pct * 100):3d}%\n{title}"
