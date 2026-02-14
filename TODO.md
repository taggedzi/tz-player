# tz-player Implementation TODO

Execution tracker derived from `SPEC.md`.
`SPEC.md` remains the source of truth.

## Status Legend

- `todo`: not started
- `in_progress`: actively being worked
- `done`: implemented, validated, and committed
- `blocked`: requires decision or external dependency

## Active Backlog

### T-026 DB Startup Failure Classification and User Guidance
- Spec Ref: Section `8` (Common failure classes), `WF-01`
- Scope:
  - Detect and classify SQLite init/access failures during startup (for example: file permission denied, path not writable, locked/corrupt DB).
  - Surface tailored user-facing remediation copy instead of generic startup failure text.
- Acceptance:
  - DB init/access failures show actionable message with what failed, likely cause, and immediate next step.
  - Recovery path remains non-blocking where possible; irrecoverable startup exits cleanly.
- Tests:
  - Startup resilience tests for representative DB failures with expected user-facing copy.
  - Regression test ensuring non-DB startup failures keep existing fallback behavior.
- Status: `todo`

### T-027 Fatal Startup Exit-Code Contract Hardening
- Spec Ref: Section `8` (Fatal startup failure non-zero exit), Section `10`
- Scope:
  - Ensure irrecoverable startup failures produce non-zero process exit codes from CLI entrypoints.
  - Ensure CLI output includes concise remediation hints for fatal startup exits.
- Acceptance:
  - Fatal startup path exits with non-zero code.
  - Fatal startup path emits user-actionable terminal output (not only log-only diagnostics).
- Tests:
  - CLI tests for fatal startup paths asserting exit code and stderr/stdout hints.
  - Regression test for successful startup retaining exit code zero behavior.
- Status: `todo`

### T-028 Unified Non-Fatal Error Surfacing (Banner/Status Channel)
- Spec Ref: Section `8` (UI errors surfaced with modal/error banner), Section `4`
- Scope:
  - Add a consistent non-fatal UI error surface for operational failures that do not require modal interruption.
  - Route key runtime failures (playback action errors, visualizer fallbacks, cache/service warnings) through this surface.
- Acceptance:
  - Users can see clean, actionable runtime errors without relying on logs.
  - Error surface does not trap focus or block keyboard-first workflows.
- Tests:
  - UI tests asserting banner/status error visibility and dismissal behavior.
  - Regression tests ensuring existing modal flows continue to work for blocking failures.
- Status: `todo`

### T-029 Visualizer Observability Completion (Load/Activate/Fallback)
- Spec Ref: Section `9` (Visualizer observability)
- Scope:
  - Ensure explicit structured logs for registry load summary, plugin activation success/failure, and fallback transitions.
  - Align log fields for these events with structured-file logging conventions.
- Acceptance:
  - Logs clearly show plugin registry composition and active visualizer transitions.
  - Fallback transitions are traceable with failed `plugin_id` and phase (`activate`/`render`).
- Tests:
  - Unit tests for expected log events and fields across load/activate/fallback paths.
  - Regression test ensuring no per-frame logging spam is introduced.
- Status: `todo`

### T-030 Configurable Local Plugin Path UX/CLI Wiring
- Spec Ref: Section `6` (Plugin discovery sources), Section `WF-07`
- Scope:
  - Add first-class runtime configuration for local visualizer plugin paths (CLI and persisted state).
  - Document configuration precedence and usage examples.
- Acceptance:
  - Users can configure one or more local plugin import paths without manual state-file editing.
  - Config precedence remains deterministic (CLI > persisted > default).
  - Startup remains resilient when configured path entries are invalid.
- Tests:
  - Parser/runtime config tests for plugin path flags and precedence.
  - Integration tests for successful path loading and invalid path degradation.
- Status: `todo`

### T-031 Final Reliability/Observability Acceptance and Docs Parity
- Spec Ref: Sections `8`, `9`, `10`, `11`
- Scope:
  - Update acceptance mapping and user docs to cover T-026..T-030 behavior.
  - Confirm workflow-to-test mapping includes new reliability and observability guarantees.
- Acceptance:
  - `docs/workflow-acceptance.md` includes the new coverage links.
  - `README.md`/`docs/usage.md` include updated troubleshooting guidance for startup and runtime errors.
- Tests:
  - N/A (docs/mapping), validated by review checklist plus full test/lint/type gates.
- Status: `todo`

## Archived Completed Work

### V3 Visualization Expansion (Extra Scope) — Completed

#### VIZ-001 Matrix Rain Visualizer Plugin
- Spec Ref: `WF-06`, Sections `5`, `6`
- Scope: Add a clean matrix-style code rain visualizer that is non-audio-reactive.
- Acceptance:
  - Plugin renders deterministic falling-code animation with smooth motion at host cadence.
  - Supports at least one green variant; optional blue/red variants exposed as selectable plugin IDs.
  - No keyboard/input starvation while active.
- Tests:
  - Unit tests for frame generation bounds and deterministic seed behavior.
  - Integration test for plugin activation, rendering, and cycling persistence.
- Status: `done`
- Commit: `e016fa0`

#### VIZ-002 Cyberpunk Terminal Ops Visualizer Plugin
- Spec Ref: `WF-06`, Sections `4`, `6`, `8`
- Scope: Add a fictional terminal-operations visualizer themed as staged song “target analysis”.
- Acceptance:
  - Renders staged fictional sequence: surveillance, vulnerability scan, ICE break, account targeting, privilege escalation, data acquisition, decryption, transfer, log cleanup.
  - Stage text is explicitly fictional and non-instructional (movie-style flavor only).
  - Uses current track metadata in output where available (title/artist/album/year).
  - Safe fallback behavior maintained on any render failure.
- Tests:
  - Unit tests for stage progression and metadata interpolation.
  - Integration test to confirm plugin remains non-blocking and survives missing metadata.
- Status: `done`
- Commit: `39ea7fe`

#### VIZ-003 Audio-Reactive VU Meter Visualizer Plugin
- Spec Ref: `WF-06`, Sections `5`, `6`, `9.1`
- Scope: Deliver `vu.reactive` as a service-driven audio-reactive visualizer consuming `AudioLevelService`.
- Acceptance:
  - Meter reflects changing audio energy during playback from effective service source (`live` or `envelope`).
  - UI indicates effective source (`live`/`envelope`/`fallback`) explicitly.
  - Behavior degrades gracefully when no signal source is available (safe fallback mode with no playback interruption).
  - Update cadence remains within host bounds without UI starvation.
- Tests:
  - Unit tests for level normalization, smoothing, clipping, and source label behavior.
  - Integration test with deterministic level provider stub and service source failover.
- Status: `done`
- Commit: `453e715`, `67c0e8f`

#### VIZ-004 Playback-Level Signal Provider Contract
- Spec Ref: Sections `5`, `6`
- Scope: Define and implement `AudioLevelService` provider contract (backend live + envelope cache + fallback).
- Acceptance:
  - Stable interface for obtaining normalized recent level samples (mono or L/R) and effective source ID.
  - Fake backend provides deterministic synthetic levels for tests.
  - VLC live provider remains capability-gated and can safely report unavailable.
  - Service source priority is deterministic: `live` -> `envelope` -> `fallback`.
- Tests:
  - Contract tests for source selection and provider shape/timing expectations.
  - Backend-specific tests for fake live provider and VLC unavailable behavior.
- Status: `done`
- Commit: `453e715`, `22463a9`

#### VIZ-005 Visualizer Catalog and UX Docs
- Spec Ref: Sections `6`, `9`, `11`
- Scope: Document plugin IDs, behavior, limitations, and troubleshooting for new visualizers.
- Acceptance:
  - `docs/visualizations.md` includes behavior/constraints for matrix, terminal-ops, and VU plugins.
  - `docs/usage.md` includes practical notes for choosing and cycling visualizers.
- Tests:
  - N/A (docs), validated by review checklist.
- Status: `done`
- Commit: `66d6195`

#### VIZ-006 Visualizer Acceptance Coverage Update
- Spec Ref: `WF-06`, Section `11`
- Scope: Extend acceptance mapping and release gate notes for added visualizer plugins.
- Acceptance:
  - `docs/workflow-acceptance.md` maps new visualizer tests.
  - Release checklist reflects any environment-gated visualizer checks.
- Tests:
  - N/A (docs), validated by review checklist.
- Status: `done`
- Commit: `66d6195`

#### VIZ-007 PCM Envelope Precompute and Time-Synced VU Source
- Spec Ref: `WF-06`, Sections `5`, `6`, `9.1`
- Scope: Add precomputed PCM level envelopes (timestamped bins) as a backend-agnostic VU signal source.
- Acceptance:
  - Decode/analyze local track audio into normalized time-bucket levels (L/R or mono) and cache by stable track fingerprint.
  - `AudioLevelService` consumes envelope levels synchronized to playback `position_ms` with interpolation and smoothing.
  - Cache invalidates when file fingerprint changes (size/mtime/hash/version key).
  - Fallback remains available when envelope data is missing or analysis fails.
- Tests:
  - Unit tests for envelope generation normalization, bucket alignment, and interpolation.
  - Unit tests for cache hit/miss/invalidation behavior.
  - Integration test proving VU uses envelope source during real playback path (without VLC callbacks).
- Status: `done`
- Commit: `22463a9`, `67c0e8f`, `b8dc538`

#### VIZ-009 FFmpeg External-Only Policy and Runtime Gating
- Spec Ref: Sections `6`, `7`, `9`, `11`
- Scope: Enforce project policy that FFmpeg is never bundled/packaged and is only used when user-installed and discoverable.
- Acceptance:
  - Envelope analysis path remains optional and checks for `ffmpeg` on PATH at runtime.
  - No release/build path attempts to download or bundle FFmpeg binaries.
  - Clear internal policy notes are documented for maintainers and release flow.
- Tests:
  - Unit tests for ffmpeg capability detection and no-ffmpeg fallback behavior.
  - Packaging/release checklist update verifying no bundled external codec binaries.
- Status: `done`
- Commit: `507283b`, `1085e73`, `80b50c6`, `66d6195`

#### VIZ-010 `doctor` Command for Dependency Diagnostics
- Spec Ref: `WF-07`, Sections `9`, `10`, `11`
- Scope: Add a CLI diagnostics command to report backend/tool readiness and remediation guidance.
- Acceptance:
  - Add command: `tz-player doctor`.
  - Reports status for:
    - `python-vlc` import and libVLC availability
    - `ffmpeg` binary discoverability/version
    - metadata reader availability (`tinytag`)
  - Exit code is non-zero when required runtime components for selected backend are missing.
  - Output includes concrete install hints and docs links.
- Tests:
  - CLI tests for success/failure exit codes and key output lines.
  - Unit tests for tool probing functions (mock PATH/process output).
- Status: `done`
- Commit: `1085e73`

#### VIZ-011 UX Wiring for Optional FFmpeg in VU/Envelope Flow
- Spec Ref: Sections `6`, `9`, `10`
- Scope: Surface actionable user messaging when ffmpeg-backed envelope analysis is unavailable.
- Acceptance:
  - Status/diagnostic text clearly indicates when envelope source is unavailable due to missing ffmpeg for non-WAV files.
  - Fallback path remains seamless (no playback interruption, no crashes).
  - Log messages are concise and useful (missing tool vs decode failure).
- Tests:
  - Integration tests for non-WAV track with missing ffmpeg -> fallback source token + messaging.
  - Regression test ensuring WAV analysis still works without ffmpeg.
- Status: `done`
- Commit: `80b50c6`

#### VIZ-012 Docs and Acceptance Mapping for Doctor + FFmpeg Policy
- Spec Ref: `WF-06`, `WF-07`, Section `11`
- Scope: Finalize user/operator docs for external-only ffmpeg usage and diagnostics workflow.
- Acceptance:
  - `docs/usage.md` documents `tz-player doctor` and interpretation.
  - `docs/media-setup.md` references doctor workflow after install.
  - `docs/workflow-acceptance.md` maps new diagnostic/policy tests.
- Tests:
  - N/A (docs), validated by review checklist.
- Status: `done`
- Commit: `66d6195`

#### VIZ-008 Next-Track Envelope Prewarm
- Spec Ref: `WF-06`, Sections `5`, `6`
- Scope: Precompute envelope for the likely next track in the background so VU is ready at track handoff.
- Acceptance:
  - When current track is playing, schedule non-blocking prewarm of predicted next item (respect repeat/shuffle mode).
  - Prewarm job is cancellable/reschedulable on queue changes, seeks, stop, or mode switches.
  - Handoff to next track should use warmed envelope via `AudioLevelService` when available, without UI/event-loop stalls.
- Tests:
  - Unit tests for next-track prediction routing (repeat/shuffle aware).
  - Integration test verifying prewarm completion and envelope availability at transition.
  - Stress test confirming no event-loop blocking under rapid navigation.
- Status: `done`
- Commit: `b8dc538`

#### VIZ-013 Release Guardrails for External Media Tooling
- Spec Ref: Sections `7`, `9`, `11`
- Scope: Add explicit release-time checks that external media binaries (VLC/FFmpeg) are never bundled by project packaging flows.
- Acceptance:
  - Release checklist explicitly verifies that build artifacts do not contain bundled `ffmpeg`/`vlc`/`libvlc` binaries.
  - CI or documented release script includes artifact inspection commands.
  - `README`/docs clearly state external-tool policy at release section.
- Subtasks:
  - Add artifact inspection step(s) to release docs/checklist.
  - Add a simple CI/docs smoke command example to inspect `dist/*` contents.
  - Add troubleshooting note for false positives on platform-specific filenames.
- Tests:
  - N/A (release/docs policy), validated by release checklist execution.
- Status: `done`
- Commit: `0c66d73`

All baseline and stabilization tasks are complete and archived here for traceability.

### P0/P1/P2 Completed
- T-001 Launch and state restore hardening — `done` — `eec7fd9`
- T-002 Playlist navigation determinism — `done` — `7572c70`
- T-003 Playback controls and routing — `done` — `cf04e9d`
- T-004 Find/search focus behavior — `done` — `9d5303a`
- T-005 Playlist editing safety and sync — `done` — `625c4f1`
- T-006 Visualizer registry and host — `done` — `212d61d`
- T-007 Visualizer selection and persistence — `done` — `7db63c5`
- T-008 Runtime config precedence and conflicts — `done` — `b59dbd8`
- T-009 Logging UX and log discoverability — `done` — `f372843`
- T-010 Error message quality pass — `done` — `b0072a9`
- T-011 Non-blocking audit for IO paths — `done` — `f3618a3`
- T-012 Opt-in performance checks — `done` — `38b134a`
- T-013 Crash-safe persistence verification — `done` — `2f64956`
- T-014 Mouse interaction acceptance coverage — `done` — `5e7b9d3`
- T-015 Docs parity and troubleshooting — `done` — `fbfffa4`
- T-016 v1 pre-release sweep — `done` — `ca3bc89`
- T-017 VLC first-track transition hardening (end-of-track advance stability + timing correctness) — `done` — `7a18103`, `6619d42`, `e16884c`, `2d8858a`, `22c5f27`, `daae237`, `56f6527`, `aca36c3`, `3e5b543`, `e0b4727`
- T-018 Visualizer local plugin discovery — `done` — `971efee`, `75a902c`
- T-019 Configurable visualizer FPS — `done` — `c68a30a`, `3fcbb11`
- T-020 Structured logging upgrade — `done` — `cd786cc`, `b17c365`
- T-021 Spec/docs metadata backend parity (TinyTag) — `done` — `8e06f9f`, `057f0c4`
- T-022 Error message quality consistency pass — `done` — `7755b1a`, `df1f448`
- T-023 State file corruption UX surfacing — `done` — `f19b69b`, `bb802c8`
- T-024 Audio level source-switch observability — `done` — `ad9eb5f`, `6d6c11f`
- T-025 Envelope cache miss/populate observability completion — `done` — `21aca99`, `e1ce0a8`
