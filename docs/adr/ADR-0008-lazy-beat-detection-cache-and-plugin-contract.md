# ADR-0008 Lazy Beat Detection Cache and Plugin Contract

- Status: Accepted
- Date: 2026-02-20

## Context

`tz-player` already provides lazy scalar level and spectrum analysis for visualizers. Beat-reactive visualizers need onset strength and beat markers, but running beat detection continuously in the UI/render loop would violate non-blocking guarantees and repeat work.

## Decision

1. Add a lazy beat pipeline aligned with existing analysis architecture:
   - analysis function: `analyze_track_beats(...)`
   - cache store: `SqliteBeatStore`
   - runtime resolver: `BeatService`
2. Persist beat frames in shared analysis cache tables with a dedicated beat frame table:
   - `analysis_type = 'beat'` in `analysis_cache_entries`
   - `analysis_beat_frames` for `(position_ms, strength_u8, is_beat, bpm)`
3. Keep beat compute on-demand:
   - schedule analysis only when active visualizer declares beat capability
   - persist once computed and reuse across restarts/playlist clears
4. Extend plugin frame payload additively (no plugin API version bump):
   - optional `beat_strength`, `beat_is_onset`, `beat_bpm`, `beat_source`, `beat_status`
   - optional capability flag `requires_beat`

## Reasoning

- Mirrors existing scalar/spectrum model, reducing architectural drift and maintenance cost.
- Preserves keyboard-first responsiveness by keeping decode/analysis off the Textual event loop.
- Additive frame fields maintain backward compatibility for existing plugins.
- Shared retention/pruning policy continues to control storage growth across all analysis types.

## Consequences

### Positive

- Beat data is lazy, cached, and reusable.
- Existing visualizers/plugins continue to work unchanged.
- New plugins can opt into beat data with explicit capability signaling.

### Tradeoffs

- Schema complexity increases (new migration and table).
- Beat quality depends on lightweight algorithm choices and may not match studio-grade detection.
- Additional background analysis jobs can increase CPU use when beat-enabled visualizers are active.

## Follow-up

- Tune beat-analysis heuristics and thresholds against larger real-world media sets.
- Add beat-aware built-in visualizer behaviors where useful.
- Expand perf/observability benchmarks specifically for beat-heavy visualization workloads.
