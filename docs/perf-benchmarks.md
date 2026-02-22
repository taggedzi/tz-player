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

Preferred workflow (persistent artifacts in `.local/perf_results/`):

```bash
.ubuntu-venv/bin/python tools/perf_run.py --scenario analysis-cache --scenario visualizer-matrix
```

Run the local-corpus user-perceived responsiveness suite:

```bash
.ubuntu-venv/bin/python tools/perf_run.py --suite user-feel --repeat 2
```

This suite composes existing opt-in scenarios (analysis/cache, track-switch, controls,
visualizers, DB, hidden-hotspot, resource trend) and writes an additional suite summary
artifact that records selected scenarios, local perf-media manifest, produced artifact
paths, and pass/fail status.

Run all supported scenarios once:

```bash
.ubuntu-venv/bin/python tools/perf_run.py
```

Repeat selected scenarios (useful for stability checks):

```bash
.ubuntu-venv/bin/python tools/perf_run.py --scenario controls --repeat 3
```

List supported scenario names:

```bash
.ubuntu-venv/bin/python tools/perf_run.py --list-scenarios
```

List supported suites:

```bash
.ubuntu-venv/bin/python tools/perf_run.py --list-suites
```

You can also pass through extra pytest flags:

```bash
.ubuntu-venv/bin/python tools/perf_run.py --scenario db-query-matrix --pytest-args -s
```

Lower-level direct pytest runs remain available:

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
`tools/perf_run.py` sets `TZ_PLAYER_PERF_RESULTS_DIR` automatically so opt-in perf tests write directly to this directory.

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

### Compare Two Suite Runs (Auto-Pair Scenario Artifacts)

Use the suite comparison tool to compare two `*_suite_summary.json` files and
automatically pair scenario artifacts by scenario group and repeat index:

```bash
.ubuntu-venv/bin/python tools/perf_compare_suite.py \
  .local/perf_results/<baseline-suite>_suite_summary.json \
  .local/perf_results/<candidate-suite>_suite_summary.json
```

Optional strict mode (non-zero exit if a suite is missing scenario artifacts that
the other suite has):

```bash
.ubuntu-venv/bin/python tools/perf_compare_suite.py --strict \
  .local/perf_results/<baseline-suite>_suite_summary.json \
  .local/perf_results/<candidate-suite>_suite_summary.json
```

### Generate a Readable HTML Report

Generate a simple HTML dashboard from one suite summary artifact:

```bash
.ubuntu-venv/bin/python tools/perf_report.py \
  .local/perf_results/<suite>_suite_summary.json
```

Open the generated report automatically (best effort):

```bash
.ubuntu-venv/bin/python tools/perf_report.py \
  .local/perf_results/<suite>_suite_summary.json \
  --open
```

Generate a comparison-oriented report (baseline + candidate suite):

```bash
.ubuntu-venv/bin/python tools/perf_report.py \
  .local/perf_results/<baseline-suite>_suite_summary.json \
  --compare-suite .local/perf_results/<candidate-suite>_suite_summary.json
```

By default the report is written next to the suite summary as:

- `*_suite_summary.report.html`

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

## Optional Deep-Profile Mode (Separate from Benchmarks)

Use deep profiling only after a benchmark identifies a regression/hotspot. Profiling overhead changes timings substantially, so do not compare profiled runs to normal benchmark artifacts.

### Profile a Pytest Perf Scenario

```bash
.ubuntu-venv/bin/python tools/perf_profile.py \
  --label controls-deep \
  --module pytest -- \
  tests/test_performance_opt_in.py -k "controls_latency_jitter_under_background_load_benchmark"
```

### Profile Artifacts

Deep-profile artifacts are written locally (git-ignored):

- `.local/perf_profiles/*.prof` (raw cProfile stats)
- `.local/perf_profiles/*.txt` (rendered `pstats` summary)

Use this mode to answer questions like:

- which functions dominate cumulative time inside a slow scenario?
- is time concentrated in Python rendering code, DB calls, logging, or state churn?
- what changed after a specific optimization attempt?
