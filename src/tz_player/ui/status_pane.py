"""Status pane with interactive slider bars."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static
from textual.widget import Widget

from tz_player.services.player_service import PlayerService, PlayerState
from tz_player.ui.slider_bar import SliderBar, SliderChanged

SPEED_MIN = 0.5
SPEED_MAX = 8.0
SPEED_STEP = 0.25


class StatusPane(Widget):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._time_bar = SliderBar(name="time", label="TIME", key_step=0.01)
        self._volume_bar = SliderBar(name="volume", label="VOL", key_step=0.05)
        self._speed_bar = SliderBar(
            name="speed",
            label="SPD",
            key_step=SPEED_STEP / (SPEED_MAX - SPEED_MIN),
        )
        self._status_line = Static("", id="status-line")
        self._player_service: PlayerService | None = None
        self._state: PlayerState | None = None

    def compose(self) -> ComposeResult:
        yield self._time_bar
        yield self._volume_bar
        yield self._speed_bar
        yield self._status_line

    def set_player_service(self, player_service: PlayerService | None) -> None:
        self._player_service = player_service

    def update_state(self, state: PlayerState) -> None:
        self._state = state
        shuffle = "on" if state.shuffle else "off"
        self._status_line.update(
            f"Status: {state.status} | repeat {state.repeat_mode} | shuffle {shuffle}"
        )
        if not self._time_bar.is_dragging:
            fraction = time_fraction(state.position_ms, state.duration_ms)
            pos_text = format_time_ms(
                state.position_ms, unknown=state.duration_ms <= 0
            )
            dur_text = format_time_ms(
                state.duration_ms, unknown=state.duration_ms <= 0
            )
            self._time_bar.set_fraction(fraction)
            self._time_bar.set_value_text(f"{pos_text}/{dur_text}")
        if not self._volume_bar.is_dragging:
            self._volume_bar.set_fraction(volume_fraction(state.volume))
            self._volume_bar.set_value_text(str(state.volume))
        if not self._speed_bar.is_dragging:
            self._speed_bar.set_fraction(speed_fraction(state.speed))
            self._speed_bar.set_value_text(f"{state.speed:.2f}x")

    async def on_slider_changed(self, event: SliderChanged) -> None:
        if self._player_service is None or self._state is None:
            return
        if event.name == "time":
            duration_ms = max(0, self._state.duration_ms)
            position_ms = int(event.fraction * duration_ms) if duration_ms else 0
            position_ms = clamp_int(position_ms, 0, duration_ms)
            pos_text = format_time_ms(position_ms, unknown=duration_ms <= 0)
            dur_text = format_time_ms(duration_ms, unknown=duration_ms <= 0)
            self._time_bar.set_value_text(f"{pos_text}/{dur_text}")
            if event.is_final and duration_ms > 0:
                self.run_worker(
                    self._player_service.seek_ms(position_ms), exclusive=False
                )
        elif event.name == "volume":
            volume = volume_from_fraction(event.fraction)
            self._volume_bar.set_value_text(str(volume))
            self.run_worker(
                self._player_service.set_volume(volume), exclusive=False
            )
        elif event.name == "speed":
            speed = speed_from_fraction(event.fraction)
            self._speed_bar.set_value_text(f"{speed:.2f}x")
            self.run_worker(self._player_service.set_speed(speed), exclusive=False)
        event.stop()


def format_time_ms(value_ms: int, *, unknown: bool = False) -> str:
    if unknown:
        return "--:--"
    total_seconds = max(0, value_ms) // 1000
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def time_fraction(position_ms: int, duration_ms: int) -> float:
    if duration_ms <= 0:
        return 0.0
    return clamp_float(position_ms / duration_ms, 0.0, 1.0)


def volume_fraction(volume: int) -> float:
    return clamp_float(volume / 100.0, 0.0, 1.0)


def volume_from_fraction(fraction: float) -> int:
    return clamp_int(int(round(fraction * 100)), 0, 100)


def speed_fraction(speed: float) -> float:
    return clamp_float((speed - SPEED_MIN) / (SPEED_MAX - SPEED_MIN), 0.0, 1.0)


def speed_from_fraction(fraction: float) -> float:
    raw = SPEED_MIN + clamp_float(fraction, 0.0, 1.0) * (SPEED_MAX - SPEED_MIN)
    return quantize_speed(raw)


def quantize_speed(speed: float) -> float:
    steps = round(speed / SPEED_STEP)
    return clamp_float(steps * SPEED_STEP, SPEED_MIN, SPEED_MAX)


def clamp_int(value: int, min_value: int, max_value: int) -> int:
    return max(min_value, min(value, max_value))


def clamp_float(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(value, max_value))
