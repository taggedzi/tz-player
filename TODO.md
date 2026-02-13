# tz-player Implementation TODO

Execution tracker derived from `SPEC.md`.  
`SPEC.md` remains the source of truth; this file tracks delivery work.

## Status Legend

- `todo`: not started
- `in_progress`: actively being worked
- `done`: implemented, validated, and committed
- `blocked`: requires decision or external dependency

## Task Template

Each task includes:
- `Spec Ref`: workflow or section reference in `SPEC.md`
- `Scope`: concrete implementation target
- `Acceptance`: measurable done criteria
- `Tests`: required automated coverage updates
- `Status`: current state
- `Commit`: fill with commit SHA when done

## P0 Core Workflows

### T-001 Launch and state restore hardening
- Spec Ref: `WF-01`, Sections `7`, `8`
- Scope: Ensure startup path is deterministic, resilient, and non-blocking for DB/state/backend init.
- Acceptance:
  - Startup reaches interactive playlist focus under nominal conditions.
  - VLC failure falls back to fake backend with actionable user-visible error.
  - Corrupt/missing state file recovers with defaults and log signal.
- Tests:
  - Extend startup resilience tests for edge cases (state read failure, DB init errors).
  - Assert no unhandled exceptions during startup flow.
- Status: `done`
- Commit: `eec7fd9`

### T-002 Playlist navigation determinism
- Spec Ref: `WF-02`, Section `4` Focus contract
- Scope: Validate cursor/viewport markers and focus-aware navigation behavior.
- Acceptance:
  - Cursor motion and scroll pinning are stable across boundary conditions.
  - Playing/current/selected markers stay correct during movement and reloads.
- Tests:
  - Add boundary tests for top/bottom transitions and empty playlist behavior.
- Status: `done`
- Commit: `7572c70`

### T-003 Playback controls and routing
- Spec Ref: `WF-03`, Section `4` Keyboard contract
- Scope: Ensure all playback bindings and status updates route consistently across focus targets.
- Acceptance:
  - All declared keys work in allowed focus states.
  - Mouse transport controls remain functional while preserving keyboard flow.
- Tests:
  - Expand key-routing matrix for all playback actions.
  - Add regressions for seek/volume/speed updates reflected in status pane.
- Status: `done`
- Commit: `cf04e9d`

### T-004 Find/search focus behavior
- Spec Ref: `WF-04`, Section `4` Keyboard + Focus contract
- Scope: Guarantee deterministic entry/exit behavior for Find mode with no keyboard traps.
- Acceptance:
  - `f`, `enter`, and `escape` behavior follows contract across modal/popup states.
  - Empty query always restores full playlist view.
- Tests:
  - Add focus transition tests around menu popup + Find interaction order.
- Status: `done`
- Commit: `9d5303a`

### T-005 Playlist editing safety and sync
- Spec Ref: `WF-05`, Sections `7`, `8`
- Scope: Keep DB/UI/transport state synchronized for add/reorder/remove/clear flows.
- Acceptance:
  - Destructive actions remain confirmation-gated.
  - Clear/reset behavior restores coherent cursor/selection/playing state.
- Tests:
  - Add integration coverage for mixed selection reorder/remove sequences.
  - Add tests for cancel paths and repeated clear actions.
- Status: `done`
- Commit: `625c4f1`

## P1 Visualization System

### T-006 Visualizer registry and host
- Spec Ref: `WF-06`, Sections `5`, `6`
- Scope: Implement visualizer registry, activation lifecycle, pane rendering host, and safe scheduling.
- Acceptance:
  - Built-in plugins discoverable by stable ID.
  - Active plugin renders bounded cadence without blocking UI loop.
  - Plugin exception triggers fallback visualizer and actionable error.
- Tests:
  - Unit tests for registry discovery, duplicate IDs, unknown ID fallback.
  - Host tests for activation/render failure fallback behavior.
- Status: `done`
- Commit: `212d61d`

### T-007 Visualizer selection and persistence
- Spec Ref: `WF-06`, Sections `6`, `7`
- Scope: Expose plugin switching flow and persist `visualizer_id` compatibility behavior.
- Acceptance:
  - User can switch visualizer.
  - Restart restores persisted plugin when available; defaults to `basic` otherwise.
- Tests:
  - Integration tests for selection persistence across restart.
  - State migration/read-compat tests for invalid or missing `visualizer_id`.
- Status: `done`
- Commit: `7db63c5`

## P1 Runtime Config, Logging, Diagnostics

### T-008 Runtime config precedence and conflicts
- Spec Ref: `WF-07`, Section `5` Runtime config precedence
- Scope: Enforce deterministic resolution for CLI flags vs persisted state vs defaults.
- Acceptance:
  - Effective config follows precedence contract.
  - `--quiet` overrides `--verbose` deterministically.
  - Backend override logic matches startup fallback behavior.
- Tests:
  - Parser and integration tests for precedence matrix.
- Status: `done`
- Commit: `b59dbd8`

### T-009 Logging UX and log discoverability
- Spec Ref: Section `9` Logging and diagnostics UX
- Scope: Ensure runtime logging flags, default levels, and log path behavior match spec and docs.
- Acceptance:
  - `--verbose`, `--quiet`, and `--log-file` behave as documented.
  - Users can identify active log destination quickly.
- Tests:
  - CLI tests for log level selection and output path handling.
- Status: `todo`
- Commit:

### T-010 Error message quality pass
- Spec Ref: Section `8` Error message quality contract
- Scope: Standardize actionable user-facing errors for common failure classes.
- Acceptance:
  - Message shape includes failure, likely cause, and next step where possible.
  - Startup fatal errors return non-zero exit from CLI entrypoints.
- Tests:
  - Add targeted tests for VLC unavailable, missing files, and init/read failures.
- Status: `todo`
- Commit:

## P2 Performance and Reliability

### T-011 Non-blocking audit for IO paths
- Spec Ref: Sections `5`, `9.1`
- Scope: Verify blocking operations are isolated off event loop and fix any violations.
- Acceptance:
  - No known direct blocking DB/file/network call on UI event loop hot paths.
  - Metadata and visualization work remain loop-safe under load.
- Tests:
  - Add regression tests around metadata debounce and UI responsiveness assumptions.
- Status: `todo`
- Commit:

### T-012 Opt-in performance checks
- Spec Ref: Section `9.1`, Section `10`
- Scope: Add opt-in performance suite for startup and interaction latency budgets.
- Acceptance:
  - Perf checks runnable via explicit opt-in command/flag.
  - Results report whether baseline targets are met.
- Tests:
  - Add perf harness/tests marked opt-in, excluded from default CI gate.
- Status: `todo`
- Commit:

### T-013 Crash-safe persistence verification
- Spec Ref: Sections `7`, `8`
- Scope: Validate atomic state writes and DB consistency expectations on interruption/failure paths.
- Acceptance:
  - No partial JSON state writes observed in simulated interruption cases.
  - DB operations fail safely without schema corruption.
- Tests:
  - Add tests for state temp-file replacement and corrupted input recovery.
- Status: `todo`
- Commit:

## P2 UX and Documentation Completeness

### T-014 Mouse interaction acceptance coverage
- Spec Ref: Section `4` Mouse contract
- Scope: Validate pointer behavior for sliders, transport, and popup dismissal interactions.
- Acceptance:
  - Mouse actions are deterministic and do not create keyboard trap states.
- Tests:
  - Add focused UI tests for mouse click/drag and focus recovery.
- Status: `todo`
- Commit:

### T-015 Docs parity and troubleshooting
- Spec Ref: Sections `9`, `11`
- Scope: Keep user/developer docs aligned with implemented behavior and diagnostics workflow.
- Acceptance:
  - `README.md` and `docs/usage.md` reflect final keybindings, flags, fallback behavior, and log guidance.
  - `docs/workflow-acceptance.md` fully maps implemented workflows.
- Tests:
  - N/A (docs-only), validated by review checklist.
- Status: `todo`
- Commit:

## Release Readiness

### T-016 v1 pre-release sweep
- Spec Ref: Section `11` Definition of Done
- Scope: Final stabilization pass and release checklist closure.
- Acceptance:
  - Required validation commands pass.
  - Known blockers resolved or formally deferred with rationale.
  - Release notes and checklist updated.
- Tests:
  - Full suite + any enabled opt-in checks.
- Status: `todo`
- Commit:
