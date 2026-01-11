"""Reusable slider bar widget for status controls."""

from __future__ import annotations

from time import monotonic

from rich.text import Text
from textual.events import Blur, Key, MouseDown, MouseMove, MouseUp
from textual.message import Message
from textual.widget import Widget


class SliderChanged(Message):
    def __init__(self, name: str, fraction: float, is_final: bool) -> None:
        super().__init__()
        self.name = name
        self.fraction = fraction
        self.is_final = is_final


class SliderBar(Widget):
    """Labeled slider with mouse + keyboard interaction."""

    DEFAULT_CSS = """
    SliderBar {
        height: 1;
    }
    SliderBar:focus {
        background: $boost;
    }
    """

    def __init__(
        self,
        *,
        name: str,
        label: str,
        fraction: float = 0.0,
        value_text: str = "",
        key_step: float = 0.02,
        emit_interval: float = 0.05,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.slider_name = name
        self.label = label
        self.fraction = _clamp_fraction(fraction)
        self.value_text = value_text
        self.key_step = key_step
        self.emit_interval = emit_interval
        self._dragging = False
        self._last_emit = 0.0
        self._last_interaction = 0.0
        self.drag_timeout = 0.5
        self._bar_start = 0
        self._bar_length = 0
        self.can_focus = True

    @property
    def is_dragging(self) -> bool:
        return self._dragging

    def set_fraction(self, fraction: float) -> None:
        self._maybe_end_stale_drag()
        self.fraction = _clamp_fraction(fraction)
        self.refresh()

    def set_value_text(self, value_text: str) -> None:
        self._maybe_end_stale_drag()
        self.value_text = value_text
        self.refresh()

    def render(self) -> Text:
        width = self.size.width
        label_text, value_text, bar_start, bar_length = self._compute_layout(width)
        self._bar_start = bar_start
        self._bar_length = bar_length
        bar = self._render_bar(bar_length)
        text = label_text
        if bar:
            text = f"{text} {bar}"
        if value_text:
            text = f"{text} {value_text}"
        if width <= 0:
            return Text("")
        return Text(text[:width], no_wrap=True)

    def on_mouse_down(self, event: MouseDown) -> None:
        if event.button != 1:
            return
        if not self._point_in_bar(event.x):
            return
        self.focus()
        self._dragging = True
        self._last_interaction = monotonic()
        self.capture_mouse()
        self._set_from_x(event.x, is_final=False)
        event.stop()

    def on_mouse_move(self, event: MouseMove) -> None:
        if not self._dragging:
            return
        self._last_interaction = monotonic()
        self._set_from_x(event.x, is_final=False)
        event.stop()

    def on_mouse_up(self, event: MouseUp) -> None:
        if not self._dragging:
            return
        self._dragging = False
        self._last_interaction = monotonic()
        self.release_mouse()
        self._set_from_x(event.x, is_final=True)
        event.stop()

    def on_blur(self, event: Blur) -> None:
        if not self._dragging:
            return
        self._dragging = False
        self._last_interaction = monotonic()
        self.release_mouse()
        self.refresh()
        event.stop()

    def on_key(self, event: Key) -> None:
        if event.key not in {"left", "right"}:
            return
        delta = -self.key_step if event.key == "left" else self.key_step
        self._set_fraction(self.fraction + delta, is_final=True)
        event.stop()

    def _compute_layout(self, width: int) -> tuple[str, str, int, int]:
        label_text = f"{self.label:<4}"
        value_text = self.value_text
        bar_length = width - len(label_text) - 2 - len(value_text)
        if bar_length < 3:
            value_text = ""
            bar_length = width - len(label_text) - 1
        if bar_length < 1:
            return label_text[:width], "", 0, 0
        bar_start = len(label_text) + 1
        return label_text, value_text, bar_start, bar_length

    def _render_bar(self, bar_length: int) -> str:
        if bar_length <= 0:
            return ""
        if bar_length == 1:
            return "●"
        thumb_index = int(round(self.fraction * (bar_length - 1)))
        thumb_index = max(0, min(thumb_index, bar_length - 1))
        chars = ["-"] * bar_length
        for index in range(thumb_index):
            chars[index] = "="
        chars[thumb_index] = "●"
        return "".join(chars)

    def _point_in_bar(self, x: int) -> bool:
        if self._bar_length <= 0:
            return False
        return self._bar_start <= x < self._bar_start + self._bar_length

    def _set_from_x(self, x: int, *, is_final: bool) -> None:
        if self._bar_length <= 0:
            return
        relative = x - self._bar_start
        fraction = 0.0 if self._bar_length == 1 else relative / (self._bar_length - 1)
        self._set_fraction(fraction, is_final=is_final)

    def _set_fraction(self, fraction: float, *, is_final: bool) -> None:
        fraction = _clamp_fraction(fraction)
        self.fraction = fraction
        now = monotonic()
        if is_final or now - self._last_emit >= self.emit_interval:
            self._last_emit = now
            self.post_message(
                SliderChanged(
                    name=self.slider_name,
                    fraction=fraction,
                    is_final=is_final,
                )
            )
        self.refresh()

    def _maybe_end_stale_drag(self) -> None:
        if not self._dragging or self._last_interaction <= 0:
            return
        if monotonic() - self._last_interaction <= self.drag_timeout:
            return
        self._dragging = False
        self.release_mouse()


def _clamp_fraction(value: float) -> float:
    return max(0.0, min(value, 1.0))
