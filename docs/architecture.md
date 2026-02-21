# Architecture

Describe the high-level design, key modules, and data flow.

## Step 1: Storage/State/Logging

- SQLite is the canonical store for playlists, tracks, and cached metadata.
- The async service layer routes blocking work through dedicated executors:
  - `run_blocking(...)` for file/DB/general IO
  - `run_cpu_blocking(...)` for CPU-heavy analysis/render tasks
- Platform-specific paths come from `platformdirs` (data/logs/config).
- Logging uses rotating files plus console output for CLI usage.
- App state persists to a small JSON file with atomic writes and safe defaults.

Schema overview:
- `tracks` stores file paths plus basic file stat cache.
- `track_meta` stores lazy-loaded metadata fields and validity flags.
- `playlists` stores named lists.
- `playlist_items` stores ordering with sparse `pos_key` values.

## Step 2: Visualizer Runtime Safety

- Visualizer plugin discovery/import is built off-loop during startup via `run_blocking(...)`.
- Frame rendering is requested by timer on the app loop, but heavy render execution is offloaded with `run_cpu_blocking(...)`.
- Render requests are coalesced: if a render is in-flight, only one pending follow-up render is queued.
- Plugin lifecycle operations (activate/render/shutdown) are serialized with a host lock to avoid cross-thread races.

Residual risk:
- Extremely slow plugin render functions can still increase visual output latency (frame skips/coalescing), but should no longer hard-block keyboard/event-loop responsiveness in normal operation.
