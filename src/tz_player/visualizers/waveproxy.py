"""Waveform-proxy visualizer using min/max channel envelopes per frame."""

from __future__ import annotations

from dataclasses import dataclass

from .base import VisualizerContext, VisualizerFrameInput


@dataclass
class WaveformProxyVisualizer:
    """Render a compact oscilloscope-style view from waveform-proxy cache data."""

    plugin_id: str = "viz.waveform.proxy"
    display_name: str = "Waveform Proxy"
    plugin_api_version: int = 1
    requires_waveform: bool = True
    _ansi_enabled: bool = True

    def on_activate(self, context: VisualizerContext) -> None:
        self._ansi_enabled = context.ansi_enabled

    def on_deactivate(self) -> None:
        return None

    def render(self, frame: VisualizerFrameInput) -> str:
        width = max(12, frame.width)
        left_min, left_max, right_min, right_max = _resolve_ranges(frame)
        lines = [
            _header(frame, width),
            _render_lane("L", left_min, left_max, width),
            _render_lane("R", right_min, right_max, width),
        ]
        return "\n".join(lines[: max(1, frame.height)])


def _header(frame: VisualizerFrameInput, width: int) -> str:
    status = frame.waveform_status or "missing"
    source = frame.waveform_source or "fallback"
    text = f"WaveformProxy [{source}/{status}]"
    return text[:width].ljust(width)


def _resolve_ranges(
    frame: VisualizerFrameInput,
) -> tuple[float, float, float, float]:
    if (
        frame.waveform_min_left is not None
        and frame.waveform_max_left is not None
        and frame.waveform_min_right is not None
        and frame.waveform_max_right is not None
    ):
        return (
            _clamp(frame.waveform_min_left),
            _clamp(frame.waveform_max_left),
            _clamp(frame.waveform_min_right),
            _clamp(frame.waveform_max_right),
        )
    left = _clamp(frame.level_left or 0.0)
    right = _clamp(frame.level_right or 0.0)
    # Fallback approximation when proxy data is unavailable.
    return (-left, left, -right, right)


def _render_lane(label: str, minimum: float, maximum: float, width: int) -> str:
    chart_width = max(6, width - 4)
    center_col = chart_width // 2
    left_col = _to_column(minimum, chart_width)
    right_col = _to_column(maximum, chart_width)
    start = min(left_col, right_col)
    end = max(left_col, right_col)

    cells = [" "] * chart_width
    cells[center_col] = "|"
    for idx in range(start, end + 1):
        cells[idx] = "─"
    cells[center_col] = "┼" if start <= center_col <= end else "|"
    return f"{label}: " + "".join(cells)


def _to_column(value: float, width: int) -> int:
    normalized = (_clamp(value) + 1.0) * 0.5
    return max(0, min(width - 1, int(round(normalized * (width - 1)))))


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))
