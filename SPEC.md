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

## 4. UX and Input Contract

### Keyboard contract

- `up/down` move playlist cursor.
- `shift+up/shift+down` reorder selected/cursor item(s).
- `v` toggles selection.
- `delete` removes selection after confirmation.
- `f` focuses Find input.
- Playback bindings (`space`, `n`, `p`, `x`, seek, volume, speed, repeat, shuffle) must work from main UI focus states.
- `escape` closes active modal/popups first; then exits Find focus or clears transient mode.

### Focus contract

- Focus transitions must be deterministic.
- No keyboard trap states are allowed.
- Visible focus indicator must exist for interactive elements.

## 5. Architecture Constraints

- Python package under `src/tz_player`.
- TUI framework: `textual`.
- Persistence: SQLite via `PlaylistStore`.
- Metadata read via `mutagen`.
- Playback through `PlaybackBackend` abstraction.
- Blocking IO must remain off the main loop (`asyncio.to_thread` or equivalent).

## 6. Data and State Requirements

- Canonical media/playlist data lives in SQLite.
- App UI/transport settings live in JSON state file.
- State writes must be atomic or crash-safe.
- Duplicate media entries in playlist are supported via playlist item identity.

## 7. Reliability and Error Handling

- User-visible operations must fail with actionable messages, not raw tracebacks.
- UI errors should be logged and surfaced with modal/error banner.
- Startup errors must degrade gracefully where possible.
- No operation should leave app in partially-updated UI without recovery path.

## 8. Observability

- Structured logging configured by CLI flags.
- Log path stored under platform data/config directories.
- Sensitive data (credentials, secrets) must not be logged.

## 9. Testing and Quality Gates

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

## 10. Definition of Done (v1 production-ready target)

A milestone is done when:

- Behavior matches this spec for affected workflows.
- Tests are added/updated and pass in CI.
- Docs (`README.md`, `docs/usage.md`, and relevant ADRs) are updated.
- No known blocker remains for keyboard navigation or core playback controls.

## 11. Delivery Plan (high-level)

1. Stabilize current app: keyboard/focus regression fixes and test hang resolution.
2. Harden playlist/search behavior and edge cases.
3. Improve error handling and startup resilience.
4. Close production checklist release blockers.
