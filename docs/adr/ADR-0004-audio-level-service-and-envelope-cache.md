# ADR-0004 - Shared AudioLevelService with SQLite Envelope Cache

- Status: Accepted
- Date: 2026-02-14
- Deciders: Project owner and implementation agent

## Context

`tz-player` now includes sound-reactive visualization goals (for example `vu.reactive`). A direct backend-only live-level approach is not consistently portable across environments, especially for VLC/runtime packaging variants. At the same time, multiple future plugins are expected to consume the same sound-level data.

Without a shared service, each plugin would need to implement its own decode, caching, error handling, and fallback logic, creating duplication and inconsistent behavior.

## Decision

Adopt a shared `AudioLevelService` that provides normalized time-synced level data to visualizers with deterministic source selection:

- Source priority:
  1. live backend level samples (when backend capability exists),
  2. precomputed PCM envelope cache stored in SQLite,
  3. plugin-safe fallback behavior.
- Envelope cache is keyed by stable track fingerprint and analysis version.
- Envelope analysis runs off-loop in background workers and never blocks render/UI paths.
- Service exposes effective source metadata (`live`, `envelope`, `fallback`) for observability and UI labeling.
- Service supports next-track prewarm analysis based on predicted next item under current repeat/shuffle policy.
- Prewarm jobs are cancellable/reschedulable when playback context changes.

## Consequences

Positive:

- Single reusable data pipeline for all audio-reactive visualizations.
- Better cross-platform reliability versus backend-specific realtime tapping only.
- Reduced repeated compute after first analysis due to SQLite cache persistence.
- Deterministic fallback behavior when live sampling is unavailable or analysis fails.

Negative:

- Adds service and cache schema complexity.
- Requires invalidation/versioning strategy for stale envelope data.
- Introduces background job orchestration for prewarm and cancellation handling.

## Alternatives Considered

- Backend-only live sampling for all reactive plugins.
  - Rejected due to portability/capability variability.
- Per-plugin analysis/caching logic.
  - Rejected due to duplication and inconsistent fallback behavior.
- Running fake and VLC backends in lockstep for visualization.
  - Rejected as high-complexity drift-prone architecture.

## Follow-up Work

- Add DB schema and migration for envelope cache tables.
- Implement `AudioLevelService` source selection and provider contract.
- Wire `vu.reactive` to service source metadata and level payloads.
- Add prewarm scheduling integrated with next-track prediction.
- Add tests for cache hit/miss/invalidation, source failover, and non-blocking behavior.
