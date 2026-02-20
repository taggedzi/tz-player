# Play Selected Track Workflow

This document maps the exact method chain when a user presses Play on a selected track, across UI, app, service, backend, and UI refresh.

## 1. Scope

- Included:
  - Keyboard `Enter` on playlist row (`play_selected`)
  - Transport PLAY button / `space` flow (`toggle_play`) when idle/stopped
  - `PlayerService.play_item(...)` chain
  - Backend play call and emitted backend events
  - Resulting `PlayerStateChanged` / `TrackChanged` UI updates
- Excluded:
  - Next/previous/repeat/shuffle progression after natural track end
  - Seek/volume/speed workflows

## 2. Entrypoints

- Playlist keyboard play:
  - `src/tz_player/ui/playlist_pane.py:77` binds `enter` -> `play_selected`
  - `src/tz_player/ui/playlist_pane.py:597` `PlaylistPane.action_play_selected()`
  - `src/tz_player/app.py:502` `TzPlayerApp.action_play_selected()`
- Transport/button play:
  - `src/tz_player/ui/transport_controls.py:147` posts `TransportAction("toggle_play")`
  - `src/tz_player/ui/playlist_pane.py:235` routes to `app.action_play_pause()`
  - `src/tz_player/app.py:458` `TzPlayerApp.action_play_pause()`

## 3. Main Flow

1. User triggers play intent.
- `Enter` in playlist calls `PlaylistPane.action_play_selected()` which dispatches `app.action_play_selected()` via `run_worker(...)`.
- Transport PLAY (or `space`) routes to `app.action_play_pause()`.

2. App resolves target item and delegates to service.
- `action_play_selected()` gets `cursor_id` via `PlaylistPane.get_cursor_item_id()` and calls:
  - `await self.player_service.play_item(self.playlist_id, cursor_id)`
  - (`src/tz_player/app.py:502`)
- `action_play_pause()` does the same only when current status is `idle`/`stopped` (otherwise toggles pause):
  - (`src/tz_player/app.py:458`)

3. `PlayerService.play_item(...)` applies loading state.
- Sets state to `loading`, sets playlist/item IDs, resets position/duration/levels/error.
- Emits `PlayerStateChanged` immediately via `_emit_state()`.
- (`src/tz_player/services/player_service.py:156`)

4. Track resolution and backend start.
- Service asks app-provided track lookup:
  - `track_info = await self._track_info_provider(playlist_id, item_id)`
- On success, service calls backend:
  - `await self._backend.play(item_id, track_info.path, 0, duration_ms=...)`
- Then sets local state `playing`, emits:
  - `TrackChanged(track_info)`
  - `PlayerStateChanged(state)`
- (`src/tz_player/services/player_service.py:180`, `src/tz_player/services/player_service.py:207`, `src/tz_player/services/player_service.py:235`)

5. App receives service events and updates UI.
- `TzPlayerApp._handle_player_event(...)` handles:
  - `PlayerStateChanged`:
    - updates `self.player_state`
    - sets `playing_item_id` in playlist pane
    - updates status pane
    - updates transport controls
    - schedules debounced state persistence
  - `TrackChanged`:
    - updates current-track pane text
    - schedules envelope analysis
    - may schedule metadata refresh worker
- (`src/tz_player/app.py:649`)

## 4. Backend-Specific Event Chain

Both backends are wired through:

- `PlayerService.__init__` -> `self._backend.set_event_handler(self._handle_backend_event)`
- (`src/tz_player/services/player_service.py:131`)

### Fake backend

- `FakePlaybackBackend.play(...)` emits, in order:
  - `StateChanged("loading")`
  - `MediaChanged(duration)`
  - `PositionUpdated(position, duration)`
  - `StateChanged("playing")`
- (`src/tz_player/services/fake_backend.py:72`)

### VLC backend

- `VLCPlaybackBackend.play(...)` submits command to worker thread (`_submit("play", ...)`).
- Thread executes `player.set_media(...)` + `player.play()`.
- Thread poll loop emits `StateChanged`, `MediaChanged`, and `PositionUpdated` as VLC state changes.
- (`src/tz_player/services/vlc_backend.py:79`, `src/tz_player/services/vlc_backend.py:183`, `src/tz_player/services/vlc_backend.py:161`)

## 5. Backend Event Normalization -> UI

1. Backend event arrives at `PlayerService._handle_backend_event(...)`.
- Updates internal `PlayerState` based on event type (`PositionUpdated`, `MediaChanged`, `StateChanged`, `BackendError`).
- Emits `PlayerStateChanged` when state changes.
- (`src/tz_player/services/player_service.py:448`)

2. App handler runs again.
- `TzPlayerApp._handle_player_event(...)` refreshes UI pieces as above, so transport/time/status keep tracking backend progression.
- (`src/tz_player/app.py:649`)

3. Polling loop supplements backend events.
- `PlayerService._poll_position()` periodically samples position/duration/state/levels and may emit additional `PlayerStateChanged`.
- (`src/tz_player/services/player_service.py:672`)

## 6. Error Handling in this Flow

- If no track info is found, service emits `status="error"` with user-facing guidance.
- If backend `play(...)` raises, service emits `status="error"` with detail.
- App surfaces runtime notice from `PlayerState.error` in status pane.
- (`src/tz_player/services/player_service.py:191`, `src/tz_player/services/player_service.py:213`, `src/tz_player/app.py:657`)

## 7. Practical Distinction

- `Enter` on playlist row always means "play this selected item now" (`action_play_selected` path).
- Transport PLAY / `space` means toggle transport state:
  - if idle/stopped (or no current item), it starts selected item
  - if already playing/paused, it toggles pause
- (`src/tz_player/app.py:458`, `src/tz_player/app.py:502`)
