# tz-player Implementation TODO

Execution tracker derived from `SPEC.md`.
`SPEC.md` remains the source of truth.

## Status Legend

- `todo`: not started
- `in_progress`: actively being worked
- `done`: implemented, validated, and committed
- `blocked`: requires decision or external dependency

## Active Backlog

## V3 Visualization Expansion (Extra Scope)

### VIZ-001 Matrix Rain Visualizer Plugin
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

### VIZ-002 Cyberpunk Terminal Ops Visualizer Plugin
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

### VIZ-003 Audio-Reactive VU Meter Visualizer Plugin
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
- Status: `in_progress`
- Commit:

### VIZ-004 Playback-Level Signal Provider Contract
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
- Status: `in_progress`
- Commit:

### VIZ-005 Visualizer Catalog and UX Docs
- Spec Ref: Sections `6`, `9`, `11`
- Scope: Document plugin IDs, behavior, limitations, and troubleshooting for new visualizers.
- Acceptance:
  - `docs/visualizations.md` includes behavior/constraints for matrix, terminal-ops, and VU plugins.
  - `docs/usage.md` includes practical notes for choosing and cycling visualizers.
- Tests:
  - N/A (docs), validated by review checklist.
- Status: `todo`
- Commit:

### VIZ-006 Visualizer Acceptance Coverage Update
- Spec Ref: `WF-06`, Section `11`
- Scope: Extend acceptance mapping and release gate notes for added visualizer plugins.
- Acceptance:
  - `docs/workflow-acceptance.md` maps new visualizer tests.
  - Release checklist reflects any environment-gated visualizer checks.
- Tests:
  - N/A (docs), validated by review checklist.
- Status: `todo`
- Commit:

### VIZ-007 PCM Envelope Precompute and Time-Synced VU Source
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
- Status: `todo`
- Commit:

### VIZ-008 Next-Track Envelope Prewarm
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
- Status: `todo`
- Commit:

## Archived Completed Work

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
