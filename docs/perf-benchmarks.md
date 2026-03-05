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

## Native Spectrum Helper POC Workflow (Local/Dev)

This repo includes a local/dev POC path for an optional native spectrum helper
used by the `analysis-cache` benchmark and a focused `analysis-bundle-sw`
benchmark (`spectrum + waveform`, no beat). The helper is selected via:

- `TZ_PLAYER_NATIVE_SPECTRUM_HELPER_CMD`

Current helper implementations (local/dev only):

- Python stub helper: `tools/native_spectrum_helper_stub.py`
- Compiled C helper POC: `tools/native_spectrum_helper_c_poc.c`
  - WAV decode path built in
  - non-WAV decode via local `ffmpeg` subprocess

### POC Prerequisites

- `.ubuntu-venv/bin/python`
- `ffmpeg` on `PATH` (required for MP3/non-WAV corpus analysis)
- `gcc` on `PATH` (only for compiled C helper POC)

### Fast Path: Helper POC Runner Script

Use the local helper benchmark runner script (builds the C helper automatically
when `--helper c` is selected):

```bash
bash tools/run_native_spectrum_helper_poc_bench.sh --helper c
```

Run the focused bundle benchmark that can exercise the helper-only
`spectrum+waveform` path (no beat):

```bash
bash tools/run_native_spectrum_helper_poc_bench.sh \
  --helper c \
  --scenario analysis-bundle-sw
```

Run against a small subset corpus while iterating:

```bash
bash tools/run_native_spectrum_helper_poc_bench.sh \
  --helper c \
  --media-dir /tmp/tz_player_perf_mp3_subset \
  --label native-cli-c-poc-subset
```

Use the Python stub helper (increase timeout to avoid false fallbacks on larger MP3s):

```bash
bash tools/run_native_spectrum_helper_poc_bench.sh \
  --helper stub \
  --timeout-s 30 \
  --media-dir /tmp/tz_player_perf_mp3_subset \
  --label native-cli-stub-subset
```

### Manual Env-Var Invocation (Equivalent)

Compiled helper:

```bash
bash tools/build_native_spectrum_helper_c_poc.sh /tmp/native_spectrum_helper_c_poc
env \
  TZ_PLAYER_RUN_PERF=1 \
  TZ_PLAYER_NATIVE_SPECTRUM_HELPER_CMD=/tmp/native_spectrum_helper_c_poc \
  .ubuntu-venv/bin/python tools/perf_run.py --scenario analysis-cache --repeat 1 --label native-cli-c-poc
```

Python stub helper:

```bash
env \
  TZ_PLAYER_RUN_PERF=1 \
  TZ_PLAYER_NATIVE_SPECTRUM_HELPER_CMD=".ubuntu-venv/bin/python tools/native_spectrum_helper_stub.py" \
  TZ_PLAYER_NATIVE_SPECTRUM_HELPER_TIMEOUT_S=30 \
  .ubuntu-venv/bin/python tools/perf_run.py --scenario analysis-cache --repeat 1 --label native-cli-stub
```

### Windows Local Build/Run (Dev POC)

Windows support for the compiled helper is still local/dev POC quality, but the
repo now includes a PowerShell build helper:

- `tools/build_native_spectrum_helper_c_poc.ps1`

Prerequisites (Windows):

- `ffmpeg.exe` on `PATH` (required for MP3/non-WAV decode)
- one C compiler on `PATH`:
  - `cl.exe` (Visual Studio Developer PowerShell), or
  - `gcc.exe` / `clang.exe` (MinGW/LLVM)

Build (PowerShell):

```powershell
powershell -ExecutionPolicy Bypass -File tools/build_native_spectrum_helper_c_poc.ps1 `
  -OutPath "$env:TEMP\native_spectrum_helper_c_poc.exe"
```

The script will try to auto-detect Visual Studio Build Tools via `vswhere.exe`
and re-run itself through `VsDevCmd.bat` when `cl.exe` is not already on
`PATH`. If that fails, open `Developer PowerShell for VS` and run the same
command again.

Quick helper smoke invocation (PowerShell; replace track path):

```powershell
$helper = "$env:TEMP\native_spectrum_helper_c_poc.exe"
$req = @{
  schema = "tz_player.native_spectrum_helper_request.v1"
  track_path = "C:\path\to\track.mp3"
  spectrum = @{
    mono_target_rate_hz = 11025
    hop_ms = 40
    band_count = 8
    max_frames = 100
  }
  beat = @{
    hop_ms = 40
    max_frames = 100
  }
  waveform_proxy = @{
    hop_ms = 20
    max_frames = 200
  }
} | ConvertTo-Json -Depth 4 -Compress

$req | & $helper
```

Using the helper from Python perf runs on Windows (PowerShell):

```powershell
$env:TZ_PLAYER_RUN_PERF = "1"
$env:TZ_PLAYER_NATIVE_SPECTRUM_HELPER_CMD = "$env:TEMP\native_spectrum_helper_c_poc.exe"
$env:TZ_PLAYER_NATIVE_SPECTRUM_HELPER_TIMEOUT_S = "30"
python tools/perf_run.py --scenario analysis-cache --repeat 1 --label native-cli-c-poc-win
```

Notes:

- The Windows helper `ffmpeg` path now uses `CreateProcessA` + pipes (not shell-string execution).
- This workflow is documented from Linux-side development and is not yet runtime-validated on Windows in CI.

### GitHub Actions Helper Artifacts (Manual)

If you want helper binaries without installing a local compiler, use the manual
workflow:

- `.github/workflows/native-helper-artifacts.yml`

It builds and uploads helper artifacts for:

- `ubuntu-latest`
- `windows-latest`

Current scope:

- helper binary build + artifact upload only (no signing, no release publishing)
- manual trigger (`workflow_dispatch`)

### Helper/Backend Metadata in Artifacts and Reports

The `analysis-cache` benchmark and focused `analysis-bundle-sw` benchmark record
helper/backend metadata, including:

- per-track:
  - `analysis_backend`
  - `spectrum_backend`
  - `beat_backend`
  - `analysis_fallback_reason`
  - `native_helper_version`
  - `duplicate_decode_for_mixed_bundle`
  - `waveform_proxy_backend` (`analysis-bundle-sw` includes this explicitly)
- aggregate:
  - `analysis_backend_counts`
  - `beat_backend_counts`
  - `waveform_proxy_backend_counts`
  - `analysis_fallback_reason_counts` (when non-empty)
  - helper command / timeout metadata

`tools/perf_compare_suite.py` and `tools/perf_report.py` surface backend/helper
metadata summaries and warnings.

### `tracks_analyzed=0` Warning (Common Causes)

If compare/report output shows `zero_tracks_analyzed=...` warnings:

- local corpus requires `ffmpeg` (for example MP3 files) and `ffmpeg` is not on `PATH`
- helper timeout is too low (especially the Python stub helper)
- selected files are unsupported or failed to decode

### Current POC Findings (Local, Directional)

These are machine- and corpus-dependent, but current local runs showed:

- The Python stub helper is useful for contract/plumbing validation but can hit helper
  timeout on larger MP3s unless timeout is increased (for example `30s`).
- The compiled C helper POC with `ffmpeg` decode (`c-poc-ffmpeg-v2`) produced strong
  cold-path improvements versus the Python stub helper on a small MP3 subset
  (`analysis-cache` scenario), including large reductions in:
  - `bundle_decode_ms`
  - `bundle_analyze_ms`
  - `bundle_total_ms`
  - `bundle_spectrum_ms`
- A focused `analysis-bundle-sw` benchmark is available to measure the newer
  helper-only `spectrum+waveform` optimization path without beat-path noise.

Treat these as directional POC evidence. The mixed bundle path still uses duplicate
decode (`native spectrum + Python beat/waveform`) and is not yet a final architecture.

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
