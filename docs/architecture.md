# Architecture

Describe the high-level design, key modules, and data flow.

## Step 1: Storage/State/Logging

- SQLite is the canonical store for playlists, tracks, and cached metadata.
- The async service layer wraps blocking SQLite/file IO in `asyncio.to_thread`.
- Platform-specific paths come from `platformdirs` (data/logs/config).
- Logging uses rotating files plus console output for CLI usage.
- App state persists to a small JSON file with atomic writes and safe defaults.

Schema overview:
- `tracks` stores file paths plus basic file stat cache.
- `track_meta` stores lazy-loaded metadata fields and validity flags.
- `playlists` stores named lists.
- `playlist_items` stores ordering with sparse `pos_key` values.
