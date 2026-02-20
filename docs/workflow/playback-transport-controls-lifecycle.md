# Playback Transport Controls Lifecycle

This document maps the lifecycle for transport controls: play/pause, stop, next, previous, seek, repeat, and shuffle.

## 1. Scope

- Included:
  - Keyboard transport actions
  - Transport footer button actions
  - App action handlers
  - `PlayerService` transport/repeat/shuffle behavior
  - Backend event normalization and resulting UI refresh
- Excluded:
  - Detailed "play selected track" chain (documented separately)
  - Slider-specific interactions for time/volume/speed (documented separately)

See also: `docs/workflow/play-selected-track.md`.

## 2. Input Entry Points

### Global app key bindings

In `src/tz_player/app.py:240`:

- `space` -> `play_pause`
- `n` -> `next_track`
- `p` -> `previous_track`
- `x` -> `stop`
- `left` / `right` -> seek ±5s
- `shift+left` / `shift+right` -> seek ±30s
- `home` / `end` -> seek start/end
- `r` -> repeat mode cycle
- `s` -> shuffle toggle

### Transport footer buttons

`TransportControls` emits high-level messages:

- `TransportAction("prev" | "toggle_play" | "stop" | "next")`
- `ToggleRepeat`
- `ToggleShuffle`
- `src/tz_player/ui/transport_controls.py:147`

`PlaylistPane` routes these to app actions:

- `on_transport_action(...)` -> `app.action_*`
- `on_toggle_repeat(...)` -> `app.action_repeat_mode()`
- `on_toggle_shuffle(...)` -> `app.action_shuffle()`
- `src/tz_player/ui/playlist_pane.py:235`

## 3. App Action Layer

Transport app actions delegate into `PlayerService`:

- `action_play_pause()` -> `play_item(...)` when idle/stopped or no active item, else `toggle_pause()`
- `action_stop()` -> `stop()`
- `action_next_track()` -> `next_track()`
- `action_previous_track()` -> `previous_track()`
- `action_seek_*()` -> `seek_delta_ms(...)` / `seek_ratio(...)`
- `action_repeat_mode()` -> `cycle_repeat_mode()`
- `action_shuffle()` -> `toggle_shuffle(anchor_item_id=...)`
- `src/tz_player/app.py:458`

## 4. PlayerService Behavior

### Core transport methods

In `src/tz_player/services/player_service.py`:

- `toggle_pause()` toggles state and calls backend `toggle_pause`, then emits state.
- `stop()` sets `stopped`, resets position/levels, calls backend `stop`, then emits state.
- `seek_ratio`, `seek_ms`, `seek_delta_ms` clamp target position, call backend `seek_ms`, emit state.
- `next_track()` and `previous_track()` apply repeat/shuffle policies and call `play_item(...)` or `stop()`.

### Repeat and shuffle

- `cycle_repeat_mode()` rotates `OFF -> ONE -> ALL -> OFF`.
- `toggle_shuffle()` toggles flag and builds/clears deterministic shuffle order.
- `next_track()` / `previous_track()` use shuffle order when enabled.
- `src/tz_player/services/player_service.py:324`

### State emission

Most action methods end with `_emit_state()` which emits `PlayerStateChanged`.

## 5. Backend Event -> App UI Updates

1. Backend events are normalized by `PlayerService._handle_backend_event(...)`:
- Handles `PositionUpdated`, `MediaChanged`, `StateChanged`, `BackendError`
- Updates service state and emits `PlayerStateChanged`
- `src/tz_player/services/player_service.py:448`

2. App receives events in `TzPlayerApp._handle_player_event(...)`:
- Updates `self.player_state`
- Updates currently-playing row highlight in playlist pane
- Updates status pane and transport controls
- Schedules persisted-state save
- `src/tz_player/app.py:649`

3. Transport footer visual state refresh:
- `TransportControls.update_from_state(...)` updates track counter, repeat/shuffle labels, PLAY/PAUSE label
- `src/tz_player/ui/transport_controls.py:126`

## 6. Behavior Notes

- Previous-track special case: if current position > 3s, `previous_track()` seeks to track start instead of moving to prior item.
- End-of-track progression is handled via backend events and poll heuristics, then routed through repeat/shuffle policy.
- Manual stop sets a stop latch to avoid misclassifying manual stop as natural track-end progression.

## 7. Failure Handling

- Backend errors are converted to user-facing playback error text in player state.
- App surfaces error text as runtime notice in the status pane.
- Any backend inconsistency still flows through state events, so controls remain synchronized with normalized `PlayerState`.
