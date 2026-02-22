# Performance Media Corpus (Local Only)

Use `.local/perf_media/` for a repeatable local audio set used for manual performance checks and opt-in perf tests.

## Why

- Repeatable cache warm/cold comparisons
- Track-switch stress testing
- Realistic spectrum/beat/waveform/envelope analysis workloads
- Visualizer performance checks with known content

## Location

- Local path (ignored by git): `.local/perf_media/`
- Keep audio files out of version control
- `.gitkeep` is committed only to preserve the directory

## Suggested Corpus Mix

- 10 short tracks (1-3 min)
- 10 medium tracks (3-6 min)
- 10+ long tracks (6-12+ min)
- A few edge cases:
  - silence / near-silence
  - low-volume tracks
  - heavy bass content
  - transient-heavy drums/percussion
  - sparse piano/ambient
  - clipped/distorted content

## Formats

Recommended:

- Mostly `mp3` (matches common library behavior)
- Optional coverage: a few `flac` and/or `wav` files

## Usage Notes

- This corpus is intended for local testing only.
- Perf tests in this repo are opt-in:

```bash
TZ_PLAYER_RUN_PERF=1 .ubuntu-venv/bin/python -m pytest tests/test_performance_opt_in.py
```

- For manual checks, point `tz-player` at a playlist/library containing `.local/perf_media/` tracks and compare:
  - cold cache run (clear analysis cache first)
  - warm cache run
  - rapid next/previous track switching
  - visualizer-heavy playback (for example particle visualizers)
- For the broader opt-in benchmark/artifact workflow, see `docs/perf-benchmarks.md`.

## Naming / Organization (Optional)

You can keep files flat or group by category, e.g.:

```text
.local/perf_media/
  short/
  medium/
  long/
  edge/
```
