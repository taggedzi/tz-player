"""Mouse interaction tests for slider bar."""

from __future__ import annotations

import asyncio

import pytest
from textual.geometry import Size
from textual.message import Message

from tz_player.ui.slider_bar import SliderBar, SliderChanged


class _FakeMouseEvent:
    def __init__(self, *, x: int, button: int = 1) -> None:
        self.x = x
        self.button = button
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class _SizedSliderBar(SliderBar):
    @property
    def size(self) -> Size:  # type: ignore[override]
        return Size(30, 1)


def test_slider_bar_mouse_drag_emits_progress_and_final() -> None:
    slider = _SizedSliderBar(
        name="volume",
        label="Vol",
        fraction=0.0,
        value_text="00%",
        emit_interval=0.0,
    )
    slider.focus = lambda *args, **kwargs: None  # type: ignore[assignment]
    slider.capture_mouse = lambda *args, **kwargs: None  # type: ignore[assignment]
    slider.release_mouse = lambda *args, **kwargs: None  # type: ignore[assignment]
    emitted: list[Message] = []

    async def run() -> None:
        slider.render()
        slider.post_message = emitted.append  # type: ignore[assignment]
        down = _FakeMouseEvent(x=slider._bar_start + 1)
        move = _FakeMouseEvent(x=slider._bar_start + slider._bar_length - 1)
        up = _FakeMouseEvent(x=slider._bar_start + slider._bar_length - 1)
        slider.on_mouse_down(down)  # type: ignore[arg-type]
        slider.on_mouse_move(move)  # type: ignore[arg-type]
        slider.on_mouse_up(up)  # type: ignore[arg-type]
        assert down.stopped is True
        assert move.stopped is True
        assert up.stopped is True

    asyncio.run(run())
    assert slider.is_dragging is False
    assert len(emitted) == 3
    assert isinstance(emitted[0], SliderChanged)
    assert emitted[0].is_final is False
    assert isinstance(emitted[1], SliderChanged)
    assert emitted[1].is_final is False
    assert isinstance(emitted[2], SliderChanged)
    assert emitted[2].is_final is True
    assert emitted[2].fraction == 1.0


def test_slider_bar_rejects_invalid_constructor_values() -> None:
    with pytest.raises(ValueError, match="key_step must be > 0"):
        SliderBar(name="volume", label="Vol", key_step=0.0)
    with pytest.raises(ValueError, match="emit_interval must be >= 0"):
        SliderBar(name="volume", label="Vol", emit_interval=-0.1)


def test_slider_bar_non_finite_fraction_clamps_to_safe_default() -> None:
    slider = SliderBar(name="volume", label="Vol")
    slider.set_fraction(float("nan"))
    assert slider.fraction == 0.0
