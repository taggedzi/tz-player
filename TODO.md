# tz-player Implementation TODO

Execution tracker derived from `SPEC.md`.
`SPEC.md` remains the source of truth.

## Status Legend

- `todo`: not started
- `in_progress`: actively being worked
- `done`: implemented, validated, and committed
- `blocked`: requires decision or external dependency

## Active Backlog

### T-018 Visualizer Local Plugin Discovery
- Spec Ref: Section `6` (Plugin discovery and identity)
- Scope:
  - Add optional local visualizer discovery from configured import path(s), in addition to built-ins.
  - Keep duplicate `plugin_id` rejection semantics (first valid plugin wins, warning logged).
- Acceptance:
  - App loads built-ins plus discoverable local plugins from configured path list.
  - Invalid local plugin modules do not crash startup; errors are logged.
  - Persisted `visualizer_id` compatibility behavior remains unchanged.
- Tests:
  - Unit tests for local plugin load success and duplicate ID handling.
  - Integration test proving startup continues when a local plugin import fails.
- Status: `done`
- Commit: `971efee`

### T-019 Configurable Visualizer FPS
- Spec Ref: Section `6` (Performance and scheduling)
- Scope:
  - Add runtime-configurable visualizer cadence (bounded 2-30 FPS) with default 10 FPS.
  - Persist/recover configured cadence in app state.
- Acceptance:
  - Effective cadence obeys configured value with clamp to `[2, 30]`.
  - Invalid persisted values recover safely to default.
  - Visualizer timer interval updates from configured cadence.
- Tests:
  - Unit tests for clamp/default/read-compat behavior.
  - Integration test confirming host/timer use configured FPS.
- Status: `done`
- Commit: `c68a30a`

### T-020 Structured Logging Upgrade
- Spec Ref: Section `9` (Observability)
- Scope:
  - Upgrade logging output to structured JSON-line format for file logging while preserving readable console output.
  - Preserve existing log-level flag behavior (`--verbose`, `--quiet`, default `INFO`).
- Acceptance:
  - File logs are machine-parseable structured records (timestamp, level, logger, message, context fields when present).
  - Console logs remain human-readable for interactive troubleshooting.
  - No sensitive data regression in emitted fields.
- Tests:
  - Logging config tests for file structure and console output behavior.
  - Regression tests for CLI log-level precedence behavior.
- Status: `todo`

### T-021 Spec/Docs Metadata Backend Parity (TinyTag)
- Spec Ref: Section `5` (Architecture constraints)
- Scope:
  - Update `SPEC.md` and related docs to reflect TinyTag usage instead of mutagen.
  - Confirm acceptance/docs mapping references current metadata backend and licensing notes.
- Acceptance:
  - `SPEC.md` architecture section names TinyTag accurately.
  - Docs remain internally consistent (`README`, usage/licensing docs, acceptance mapping as needed).
- Tests:
  - N/A (docs/spec parity), validated by review checklist.
- Status: `done`
- Commit: `8e06f9f`

### T-022 Error Message Quality Consistency Pass
- Spec Ref: Section `8` (Reliability and Error Handling), Error message quality contract
- Scope:
  - Normalize user-facing error text across playback, playlist actions, and UI modals to consistently include:
    - what failed,
    - likely cause (when known),
    - immediate next step.
  - Replace terse messages (for example, generic/not-found errors) with actionable copy where user impact exists.
- Acceptance:
  - User-facing failure paths in core workflows use consistent actionable language.
  - No raw/low-context error text remains in primary UI paths.
  - Existing fallback behavior remains unchanged.
- Tests:
  - Update/add UI/service tests asserting improved message text for key error paths.
  - Regression tests ensuring failure handling still degrades safely.
- Status: `done`
- Commit: `7755b1a`

### T-023 State File Corruption UX Surfacing
- Spec Ref: Section `8` (Common failure classes), Section `WF-01`
- Scope:
  - Surface explicit in-app user notification when persisted state file is unreadable/corrupt and defaults are used.
  - Keep startup resilient (no crash, no lockup), while making recovery guidance visible without reading logs.
- Acceptance:
  - On corrupt/unreadable state file, startup continues with defaults and displays clear remediation guidance.
  - Message includes likely cause and next step (for example: reset/remove state file path).
  - Behavior remains non-blocking and does not regress startup fallback logic.
- Tests:
  - Startup resilience test for invalid/corrupt state file path that asserts user-visible messaging.
  - Regression test for normal startup path with no warning.
- Status: `done`
- Commit: `f19b69b`

### T-024 Audio Level Source-Switch Observability
- Spec Ref: Section `9` (Observability)
- Scope:
  - Add explicit log events when effective audio level source changes (`live` <-> `envelope` <-> `fallback`).
  - Include enough context for diagnosis (track path/id when available, prior source, next source, trigger reason).
- Acceptance:
  - Source transitions are logged once per transition (not per frame/tick spam).
  - Logs are emitted for startup source selection and runtime changes (seek/next/backend capability changes).
  - No impact on render/event-loop responsiveness.
- Tests:
  - Unit/integration tests asserting transition logs are emitted exactly on source changes.
  - Regression test ensuring no repeated spam when source is stable.
- Status: `done`
- Commit: `ad9eb5f`

### T-025 Envelope Cache Miss/Populate Observability Completion
- Spec Ref: Section `9` (Observability)
- Scope:
  - Complete cache observability by adding explicit per-track envelope cache miss logging and successful cache populate summary (without excessive duplication).
  - Keep existing cache hit and failure logs aligned with this flow.
- Acceptance:
  - For each analyzed track, logs can distinguish hit vs miss -> analysis -> stored outcome.
  - Duplicate/noisy logs are bounded (for example, one miss/populate chain per track analysis attempt).
  - Existing ffmpeg-missing and analysis-failure diagnostics remain intact.
- Tests:
  - Integration test for miss path logging and populate logging.
  - Regression test for hit path without miss noise.
- Status: `done`
- Commit: `21aca99`

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
