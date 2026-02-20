# Playback Time/Volume/Speed Lifecycle

This document maps control flows for time seek, volume, and speed, including both keyboard and slider-driven interactions.

## 1. Scope

- Included:
  - Keyboard controls for time/volume/speed
  - Status pane slider interactions
  - App action handlers and `PlayerService` methods
  - State update loop back into status/transport UI
- Excluded:
  - Transport actions like next/previous/stop/repeat/shuffle
  - Track-start selection flow

## 2. Entry Points

### Keyboard actions

Global bindings in `src/tz_player/app.py:240`:

- Time seek:
  - `left` / `right` -> seek ±5s
  - `shift+left` / `shift+right` -> seek ±30s
  - `home` / `end` -> seek start/end
- Volume:
  - `-` / `+` -> volume ±5
  - `shift+-` / `shift+=` -> volume ±10
- Speed:
  - `[` / `]` -> speed step ±0.25x
  - `\` -> reset speed to `1.0x`

### Slider actions

`StatusPane.on_slider_changed(...)` in `src/tz_player/ui/status_pane.py:129`:

- Time slider:
  - live-updates displayed time text while dragging
  - only commits seek on final release (`event.is_final`)
  - calls `player_service.seek_ms(position_ms)`
- Volume slider:
  - maps fraction to 0..100 and calls `player_service.set_volume(volume)`
- Speed slider:
  - maps fraction to 0.5..4.0 and quantizes to 0.25 steps
  - calls `player_service.set_speed(speed)`

## 3. App Action Layer (Keyboard Path)

In `src/tz_player/app.py`:

- Time:
  - `action_seek_back/forward` -> `player_service.seek_delta_ms(...)`
  - `action_seek_start/end` -> `player_service.seek_ratio(0.0/1.0)`
- Volume:
  - `action_volume_down/up(_big)` -> `player_service.set_volume(self.player_state.volume +/- delta)`
- Speed:
  - `action_speed_down/up` -> `player_service.change_speed(-1/+1)`
  - `action_speed_reset` -> `player_service.reset_speed()`
- `src/tz_player/app.py:528`

## 4. PlayerService Control Semantics

In `src/tz_player/services/player_service.py`:

- `seek_ratio`, `seek_ms`, `seek_delta_ms`:
  - clamp to `[0, duration_ms]`
  - call backend `seek_ms(...)`
  - emit `PlayerStateChanged`
- `set_volume`:
  - clamp to `[0, 100]`
  - call backend `set_volume(...)`
  - emit `PlayerStateChanged`
- `change_speed` / `set_speed` / `reset_speed`:
  - clamp to `[0.5, 4.0]`
  - use 0.25x stepping for `change_speed`
  - call backend `set_speed(...)`
  - emit `PlayerStateChanged`

Relevant methods:

- `src/tz_player/services/player_service.py:266`
- `src/tz_player/services/player_service.py:292`
- `src/tz_player/services/player_service.py:299`

## 5. UI Refresh Loop

1. `PlayerService` emits `PlayerStateChanged`.

2. `TzPlayerApp._handle_player_event(...)` stores latest state and updates status pane:
- `self.player_state = event.state`
- `_update_status_pane()`
- `src/tz_player/app.py:655`

3. `StatusPane.update_state(...)` redraws controls from state:
- Time text from `format_time_pair_ms`
- Time slider fraction from `time_fraction(position, duration)`
- Volume slider fraction/text
- Speed slider fraction/text
- `src/tz_player/ui/status_pane.py:86`

4. Transport footer reflects play/pause mode and track position separately:
- `PlaylistPane.update_transport_controls(...)` -> `TransportControls.update_from_state(...)`
- `src/tz_player/ui/playlist_pane.py:231`

## 6. Backend Position and Level Feeds

Even without explicit user input, background polling keeps time/progress fresh:

- `PlayerService._poll_position()` samples backend position/duration/state
- Updates `position_ms`, `duration_ms`, and audio level fields
- Emits `PlayerStateChanged` on meaningful changes
- `src/tz_player/services/player_service.py:672`

This keeps time slider and status line synchronized during playback.

## 7. Behavior Notes

- Time slider seeks only on release to avoid over-sending backend seek requests during drag.
- Volume and speed sliders apply continuously as values change.
- Keyboard and slider paths converge in `PlayerService`, so clamping/range behavior stays consistent.
