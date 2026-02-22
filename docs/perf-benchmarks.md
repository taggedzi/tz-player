# Opt-In Performance Benchmarking

This project includes a permanent, opt-in performance benchmarking harness for tracking latency and resource regressions over time.

## Goals

- Find slow paths across UI, DB, visualizers, and analysis workflows
- Capture repeatable benchmark artifacts for branch-to-branch comparison
- Surface non-obvious hotspots (high-frequency low-cost calls, background churn)
- Keep all perf checks opt-in (not part of default CI)

## Prerequisites

- Local perf media corpus (optional for media-driven scenarios):
  - See `docs/perf-media.md`
  - Default local path: `.local/perf_media/`
- Python environment:
  - `.ubuntu-venv/bin/python`

## Running Opt-In Perf Tests

Run the full opt-in perf test module:

```bash
TZ_PLAYER_RUN_PERF=1 .ubuntu-venv/bin/python -m pytest tests/test_performance_opt_in.py
```

Run a single scenario while iterating:

```bash
TZ_PLAYER_RUN_PERF=1 .ubuntu-venv/bin/python -m pytest tests/test_performance_opt_in.py -k "visualizer_matrix_benchmark_artifact"
```

## Current Benchmark Coverage (Foundations)

- Track switch + analysis preload benchmark (artifact output)
- Controls latency + jitter under background load (artifact output)
- Visualizer matrix benchmark artifacts across responsiveness profiles
- Large playlist DB query matrix with slow-query event correlation
- Hidden-hotspot call-probe sweep (cumulative time + call counts)
- Resource trend snapshots (CPU/GC/RSS best-effort across phases)

Note:

- Some scenarios currently use deterministic stubs (for example preload timing plumbing) while the harness matures toward fully real warm/cold analysis-path runs.

## Benchmark Artifacts

Benchmark artifacts are written to a local git-ignored directory:

- `.local/perf_results/`

Artifacts are JSON and can be compared across runs/branches.

### Compare Two Artifacts

Use the local comparison tool:

```bash
.ubuntu-venv/bin/python tools/perf_compare.py .local/perf_results/<baseline>.json .local/perf_results/<candidate>.json
```

Optional thresholds:

```bash
.ubuntu-venv/bin/python tools/perf_compare.py \
  --regression-pct 3.0 \
  --improvement-pct -3.0 \
  .local/perf_results/<baseline>.json \
  .local/perf_results/<candidate>.json
```

## Recommended Workflow (Repeatable)

1. Record machine context (same machine, same power mode, minimal background apps).
2. Clear/keep cache intentionally depending on the scenario:
   - cold-cache run
   - warm-cache run
3. Run selected opt-in perf scenarios and collect JSON artifacts.
4. Repeat after code changes.
5. Compare artifacts with `tools/perf_compare.py`.
6. Investigate regressions using:
   - structured perf events
   - hidden-hotspot call-probe outputs
   - resource trend snapshots

## Cold vs Warm Cache Guidance

- Cold cache:
  - Clear relevant analysis cache DB entries before the run (or use a fresh app data dir)
  - Useful for decode/analysis scheduling and cache population timing
- Warm cache:
  - Re-run same scenarios without clearing cache
  - Useful for runtime read-path and in-memory preload performance

## Interpreting Common Bottlenecks

- `visualizer_frame_loop_overrun` spikes:
  - likely render cost / plugin cost / frame loop pressure
- `playlist_store_slow_query` events:
  - likely DB query path, FTS fallback, large window, or IO contention
- high `loading` in sampling stats:
  - analysis cache misses or background analysis not finished yet
- high `db_hits` with low `memory_hits`:
  - in-memory analysis preload/cache path not warming as expected
- hidden-hotspot top cumulative methods:
  - often non-obvious UI/status/state-save churn or background coordination overhead

## Notes on Portability

- Resource metrics are best-effort and platform-dependent:
  - CPU and GC are broadly portable
  - RSS (`ru_maxrss`) availability/units vary by OS
- Compare artifacts primarily on the same machine/profile for meaningful trends.
