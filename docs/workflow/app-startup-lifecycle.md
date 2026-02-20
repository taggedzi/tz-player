# App Startup Lifecycle

This document maps the runtime startup flow for the primary `tz-player` application path.

## 1. Entrypoint Resolution

- `pyproject.toml` maps the installed `tz-player` command to `tz_player.app:main`.
- Running `tz-player` executes `main()` in `src/tz_player/app.py`.

## 2. CLI Bootstrap (`main`)

In `src/tz_player/app.py`:

1. `build_parser()` defines runtime flags and the optional `command` mode (`run` or `doctor`).
2. `args = parser.parse_args()` parses CLI input.
3. `resolve_log_level(...)` + `setup_logging(...)` initialize logging.
4. If `command == "doctor"`, diagnostics run via `run_doctor(...)`, a report is printed, and process exits.
5. Otherwise, `TzPlayerApp(...)` is constructed and `app.run()` starts the Textual event loop.

## 3. App Construction (`TzPlayerApp.__init__`)

`src/tz_player/app.py` initializes in-memory state and service placeholders:

- Theme registration and base app state.
- Playlist/data store handles.
- Playback/metadata service references (initially `None`).
- Visualizer references and startup failure sentinel (`startup_failed = False`).

Heavy startup side effects are intentionally deferred.

## 4. UI Composition (`compose`)

`compose()` builds the main screen tree:

- Header
- Main horizontal split
- Playlist pane
- Right pane (visualizer + current-track)
- Status pane
- Footer

This defines structure only; it does not perform backend/database startup.

## 5. Mount and Async Initialization

`on_mount()` schedules `_initialize_state()` with `asyncio.create_task(...)`.

`_initialize_state()` performs the operational bootstrap:

1. Load persisted state with `run_blocking(load_state_with_notice, state_path())`.
2. Resolve effective backend and visualizer settings from CLI overrides + persisted state.
3. Persist normalized state back to disk with `save_state(...)`.
4. Initialize playlist and envelope stores and ensure default playlist exists.
5. Build playback backend (`vlc` or `fake`), create `PlayerService`, create `MetadataService`.
6. `await player_service.start()` to bring backend online.
7. Bind services to UI panes, configure `PlaylistPane`, focus playlist, update status/transport/current-track panes.
8. Start visualizer loop and optionally show state warning modal.

If any step fails:

- Exception is logged.
- `startup_failed` is set `True`.
- Error modal is shown with user-facing guidance.

## 6. Runtime Event Routing

`PlayerService` emits domain events back into the app via `emit_event=self._handle_player_event`.

`_handle_player_event(...)` processes:

- `PlayerStateChanged`: refreshes state-dependent UI, controls, status, and debounced state persistence.
- `TrackChanged`: updates current track panel and triggers metadata/envelope background work.

User keyboard actions (`action_play_pause`, `action_seek_*`, etc.) call into `PlayerService`, which updates backend state and emits new events.

## 7. Shutdown Path

`on_unmount()` performs best-effort cleanup:

1. Stop visualizer timer/tasks.
2. Flush pending state saves.
3. Cancel envelope/prewarm background tasks.
4. Persist latest app/player state.
5. Shutdown `PlayerService` and backend.

## 8. Important Distinction: `cli.py` vs `app.py`

- `src/tz_player/cli.py` is a lightweight smoke CLI for non-UI startup checks (arg parsing + logging readiness).
- The primary user-facing runtime path is `src/tz_player/app.py` (`tz_player.app:main`).
