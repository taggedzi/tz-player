# tz-player Specification (v1)

## 1. Purpose

`tz-player` is a local-first terminal music player with a Textual TUI.

The product goal is reliable playback control and playlist management from keyboard-first workflows, with optional mouse support.

## 2. Product Scope

### In scope

- Single-user local desktop usage.
- Playlist management backed by SQLite.
- Playback via pluggable backend (`fake` and `vlc`).
- Keyboard-first interaction in the TUI.
- Persistent app state (volume, speed, repeat, shuffle, current item, backend).
- Cached metadata extraction for local files.

### Out of scope (v1)

- Streaming services.
- Multi-user/network sync.
- Remote control/API server.
- Gapless/crossfade DSP features.
- Library tagging/editing UI.

## 3. Core User Workflows

### WF-01: Launch and recover state

1. User starts `tz-player`.
2. App loads persisted state and default playlist.
3. App initializes playback backend.
4. Playlist pane is focused and usable immediately.

Acceptance criteria:
- App startup does not block indefinitely.
- If VLC backend fails, app falls back to `fake` backend and shows a clear error.
- Failure paths never leave the UI unresponsive.

### WF-02: Navigate playlist

1. User moves cursor with `up/down`.
2. View scrolls when cursor moves past viewport.
3. Selected/playing/current markers remain correct.

Acceptance criteria:
- Cursor movement is deterministic.
- Scrolling behavior preserves expected row position.
- Track counter and transport context remain consistent with cursor and playback state.

### WF-03: Playback control

User controls playback with keyboard (`space`, `n`, `p`, `x`, seek keys, volume keys, speed keys, repeat/shuffle).

Acceptance criteria:
- All declared keybindings trigger expected action when no text input is focused.
- Transport controls remain usable by mouse.
- State pane updates within one UI tick after player state change event.

### WF-04: Find/search focus behavior

1. User presses `f` to focus Find input.
2. Typing filters playlist (when enabled).
3. User can reliably return focus to playlist controls via keyboard.

Acceptance criteria:
- Entering Find mode must not trap global controls permanently.
- Escape/confirm behavior is explicit and documented.
- If search is empty, playlist behaves as normal full list.

### WF-05: Playlist editing

User can add files/folder, reorder, select, remove selected, and clear playlist.

Acceptance criteria:
- Actions are confirmed where destructive.
- DB state and UI state remain synchronized after each action.
- Clear playlist resets cursor/selection/playing state.

### WF-06: Visualization rendering and selection

1. User sees visualization output in the right-side visualizer pane during playback.
2. User can switch to another available visualizer plugin.
3. User restart preserves selected visualizer when still available.

Acceptance criteria:
- Visualization updates run without blocking keyboard interaction or transport controls.
- If a visualizer fails, app falls back to a safe visualizer and surfaces an actionable error.
- If persisted visualizer is missing, app selects default visualizer and continues startup.

### WF-07: Configure runtime behavior and diagnostics

1. User starts app with CLI flags for backend and logging behavior.
2. App resolves effective runtime config from CLI, persisted state, and defaults.
3. User can locate logs and diagnose common failures without reading source code.

Acceptance criteria:
- Config precedence is deterministic and documented.
- Logging can be increased/decreased without code changes.
- Error output includes actionable remediation for common setup failures.

## 4. UX and Input Contract

### Keyboard contract

- `up/down` move playlist cursor.
- `shift+up/shift+down` reorder selected/cursor item(s).
- `v` toggles selection.
- `delete` removes selection after confirmation.
- `a` opens/toggles the playlist Actions menu.
- `f` focuses Find input.
- Playback bindings (`space`, `n`, `p`, `x`, seek, volume, speed, repeat, shuffle) must work from main UI focus states.
- `escape` closes active modal/popups first; then exits Find focus or clears transient mode.

### Focus contract

- Focus transitions must be deterministic.
- No keyboard trap states are allowed.
- Visible focus indicator must exist for interactive elements.

### Mouse contract

- Mouse support is optional but reliable where implemented.
- Click/drag affordances for transport and slider controls must be discoverable.
- Mouse interactions must not break keyboard-first workflows or steal focus irrecoverably.
- Modal/popup dismiss behavior via pointer interactions must be deterministic.

### Visualization UX contract

- Visualizer pane must always render a valid frame (plugin output or explicit fallback message).
- Visualizer frame rate must be bounded and deterministic to avoid UI starvation.
- Visualizer behavior must degrade gracefully when paused/stopped/no track loaded.
- Visualizer selection UI (when added) must be keyboard reachable and must not trap focus.
- ANSI output is optional and gated by app state/config (`ansi_enabled`).

## 5. Architecture Constraints

- Python package under `src/tz_player`.
- TUI framework: `textual`.
- Persistence: SQLite via `PlaylistStore`.
- Metadata read via `mutagen`.
- Playback through `PlaybackBackend` abstraction.
- Blocking IO must remain off the main loop (`asyncio.to_thread` or equivalent).
- Visualizers are loaded via a plugin registry with stable plugin IDs.
- Visualizer render path must not do blocking file/db/network IO on the event loop.

### Runtime config precedence

- Precedence order must be explicit and stable:
  1. CLI flags for current run.
  2. Persisted state/settings.
  3. Built-in defaults.
- Effective backend selection follows this precedence and degrades safely to `fake` when VLC initialization fails.
- Conflicting logging flags must resolve deterministically (`--quiet` overrides `--verbose`).

## 6. Visualization plugin model (v1 target)

### Plugin discovery and identity

- Plugin discovery sources:
  - Built-in plugins shipped in `tz_player.visualizers`.
  - Optional local plugins exposed by configured import path(s).
- Each plugin has a unique, stable `plugin_id` string for persistence (`AppState.visualizer_id`).
- Duplicate IDs are rejected during registry build; app logs error and keeps first valid plugin.

### Plugin lifecycle

- Plugin instances are created by the registry/factory, not directly by UI code.
- Lifecycle hooks:
  - `on_activate(context)` called when plugin becomes active.
  - `render(frame_input) -> str` returns Textual-safe frame text.
  - `on_deactivate()` called before switching away or shutdown.
- Plugin hooks must be exception-contained by host. Unhandled plugin exceptions must not crash app.

### Frame input contract

Host provides immutable render input containing:

- Playback state: `status`, `position_s`, `duration_s`, `volume`, `speed`, `repeat_mode`, `shuffle`.
- Track context: current track ID/path and selected metadata subset when available.
- Timing context: monotonic timestamp, frame index, terminal pane width/height.
- Capability flags: ANSI enabled, Unicode fallback preference.

### Performance and scheduling

- Default render cadence target: 10 FPS.
- Supported range for configurable cadence: 2-30 FPS.
- If plugin render exceeds frame budget consistently, host throttles and logs warning.
- Any plugin-required blocking computation must run off-loop and feed cached render state.

### Safety and fallback policy

- On plugin activation/render failure, host switches to `basic` fallback visualizer.
- Fallback visualizer must always produce deterministic text output and zero external dependencies.
- User-visible error message should identify failed `plugin_id` and failure phase (activate/render).

### Persistence and compatibility

- Persist selected visualizer as `visualizer_id` in state JSON.
- Missing/invalid persisted ID resolves to default plugin (`basic`) at startup.
- State schema changes for visualizer config require migration coverage and tests.

## 7. Data and State Requirements

- Canonical media/playlist data lives in SQLite.
- App UI/transport settings live in JSON state file.
- State writes must be atomic or crash-safe.
- Duplicate media entries in playlist are supported via playlist item identity.
- Visualization selection persists via `visualizer_id` and must be forward-compatible.
- Persisted state keys should be backward-compatible where feasible; renamed keys require migration/read-compat coverage.
- Shutdown and crash recovery must preserve DB/state integrity (no partially-written JSON and no corrupt SQLite schema operations).

## 8. Reliability and Error Handling

- User-visible operations must fail with actionable messages, not raw tracebacks.
- UI errors should be logged and surfaced with modal/error banner.
- Startup errors must degrade gracefully where possible.
- No operation should leave app in partially-updated UI without recovery path.
- Visualization/plugin failures must degrade to fallback visualizer without breaking playback UI.

### Error message quality contract

- User-facing error text should include:
  - what failed,
  - likely cause (when known),
  - immediate next step.
- Common failure classes must have tailored copy:
  - missing media file/path,
  - unavailable VLC/libVLC runtime,
  - unreadable/corrupt state file,
  - DB access/init failure.
- Fatal startup failure must return non-zero exit code from CLI entrypoints.

## 9. Observability

- Structured logging configured by CLI flags.
- Log path stored under platform data/config directories.
- Sensitive data (credentials, secrets) must not be logged.
- Visualizer registry load, activation, fallback, and render overrun events should be logged.

### Logging and diagnostics UX

- Supported logging flags:
  - `--verbose` for debug-level logs,
  - `--quiet` for warning/error-only logs,
  - `--log-file` for explicit file path output.
- Default log level is `INFO` when no flag is set.
- Logs should be written to both console and file output configured by application logging setup.
- User docs must describe where logs are written and how to raise verbosity for troubleshooting.

## 9.1 Performance targets and opt-in profiling

- Performance targets (v1 baseline):
  - App startup to interactive playlist focus: <= 2.0s on a typical dev machine for small playlists (<= 500 items).
  - Keyboard action to visible UI update: <= 100ms for core controls under nominal load.
  - Metadata refresh scheduling must not block render/input loop.
- Performance regression checks are opt-in for local and CI workflows.
- Optional performance checks must be clearly labeled and skippable without blocking standard functional CI.

## 10. Testing and Quality Gates

Required checks before release:

- `ruff check .`
- `ruff format --check .`
- `mypy src`
- `pytest`

Quality expectations:

- Tests cover keyboard flows, focus flows, playback control routing, playlist mutations, and state persistence.
- Regressions in keybindings/focus require dedicated tests.
- No test may hang indefinitely; long-running tests require explicit timeout strategy.
- Workflow-to-test mapping is maintained in `docs/workflow-acceptance.md`.
- Visualization tests cover registry loading, ID persistence, fallback behavior, and render cadence bounds.
- Add opt-in performance/regression tests for startup and interaction latency before v1 release sign-off.

## 11. Definition of Done (v1 production-ready target)

A milestone is done when:

- Behavior matches this spec for affected workflows.
- Tests are added/updated and pass in CI.
- Docs (`README.md`, `docs/usage.md`, and relevant ADRs) are updated.
- No known blocker remains for keyboard navigation or core playback controls.
- No known blocker remains for visualization fallback safety or plugin loading determinism.

## 12. Delivery Plan (high-level)

1. Stabilize current app: keyboard/focus regression fixes and test hang resolution.
2. Harden playlist/search behavior and edge cases.
3. Improve error handling and startup resilience.
4. Implement visualization registry, fallback visualizer, and plugin switching flow.
5. Close production checklist release blockers.
