# ADR-0006 Lazy Persistent Analysis Cache (Scalar + Spectrum)

- Status: Accepted
- Date: 2026-02-20

## Context

`tz-player` needs audio-reactive visualizations that can consume scalar level and FFT-like spectrum data without blocking the Textual event loop. Precomputing everything at import/startup is wasteful, while storing nothing causes repeated compute and data loss on playlist clear.

## Decision

1. Use a generic SQLite analysis cache model keyed by media fingerprint + analysis type + params:
   - `analysis_cache_entries`
   - `analysis_scalar_frames`
   - `analysis_spectrum_frames`
2. Keep scalar and spectrum analysis lazy:
   - compute only when requested by active visualization flows
   - persist once computed for reuse across restarts
3. Keep render paths non-blocking:
   - visualizer `render(...)` only consumes frame payload
   - scheduling/compute/persistence run in background tasks + executor offload
4. Extend plugin frame payload additively (no API version bump):
   - optional `level_status`, `spectrum_bands`, `spectrum_source`, `spectrum_status`
   - optional plugin capability flag `requires_spectrum` to opt into spectrum sampling
5. Preserve backward compatibility:
   - legacy plugins without `requires_spectrum` continue to run unchanged
   - fallback behavior remains deterministic when analysis is `loading|missing|error`

## Consequences

### Positive

- Analysis survives playlist clear and app restart.
- Compute cost is paid only when needed.
- Existing plugins keep working without migration.
- Host can avoid spectrum work unless the active plugin opts in.

### Tradeoffs

- DB schema and migration complexity increases.
- Spectrum generation quality/performance is bounded by lightweight implementation choices.
- Full untrusted plugin sandboxing remains out of scope.

## Follow-up

- Implement retention pruning policy execution and observability events.
- Continue acceptance/docs mapping updates for lazy analysis workflows.
