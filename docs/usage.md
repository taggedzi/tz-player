# Usage

Run the TUI:

```
tz-player
```

Run environment diagnostics:

```
tz-player doctor
```

Select a playback backend:

```
tz-player --backend vlc
```

Add local visualizer plugin discovery paths (repeatable):

```
tz-player --visualizer-plugin-path ./my_visualizers --visualizer-plugin-path mypkg.visualizers
```

Set local plugin security policy mode:

```
tz-player --visualizer-plugin-security warn
```

Set local plugin runtime mode:

```
tz-player --visualizer-plugin-runtime isolated
```

Set visualizer responsiveness profile:

```
tz-player --visualizer-responsiveness balanced
```

Notes:
- Default backend is `vlc`.
- The VLC backend requires VLC/libVLC installed on your system.

GUI entrypoint supports the same flag:

```
python -m tz_player.gui --backend vlc
```

Logging and diagnostics:
- Default log level is `INFO`.
- `--verbose` sets log level to `DEBUG`.
- `--quiet` sets log level to `WARNING` (takes precedence over `--verbose`).
- `--log-file /path/to/tz-player.log` writes logs to an explicit file path.
- `--visualizer-plugin-path <path_or_module>` adds local visualizer plugin discovery entries for this run (repeatable; CLI overrides persisted list).
- `--visualizer-plugin-security <off|warn|enforce>` controls static safety checks for local plugin source.
  - `warn` (default): plugin loads, warning is logged/notified when risky patterns are detected.
  - `enforce`: plugin is blocked when risky patterns are detected.
  - `off`: skip static safety preflight checks.
- `--visualizer-plugin-runtime <in-process|isolated>` controls how local plugins execute.
  - `in-process` (default): local plugins run in the app process.
  - `isolated`: local plugins run in a subprocess with RPC timeouts and fail-closed fallback behavior.
- `--visualizer-responsiveness <safe|balanced|aggressive>` selects profile defaults for visualizer responsiveness.
  - `safe`: lower CPU, conservative responsiveness defaults.
  - `balanced`: recommended default profile.
  - `aggressive`: higher responsiveness, higher CPU cost.
  - Profiles also tune analysis freshness defaults (FFT/beat hop) and player polling cadence.
  - Precedence for render cadence:
    - `--visualizer-fps` (explicit) overrides profile defaults.
    - without explicit FPS, `--visualizer-responsiveness` sets profile-default FPS.
    - persisted FPS is used only when no CLI FPS/profile override is provided.
- Without `--log-file`, logs are written to the app log directory as `tz-player.log`.
  - Typical default location pattern: `<user_data_dir>/logs/tz-player.log`.
- TUI/GUI runs write logs to file by default (console log streaming is disabled to avoid drawing over the TUI).
- The non-TUI `doctor` path still prints diagnostics to stdout.
- `doctor` command behavior:
  - `tz-player doctor` checks `tinytag`, `vlc/libvlc`, and `ffmpeg`.
  - Exit code is `0` when required checks pass for the selected backend.
  - Exit code is non-zero when required checks fail (for example `--backend vlc` without libVLC).
  - Example: `tz-player doctor --backend vlc`

Theme:
- The header theme selector includes a custom `cyberpunk-clean` theme using teal structure with sparing yellow highlights.

Current keys:
- `up` / `down`: move cursor up/down in the playlist
- `pageup` / `pagedown`: move cursor and viewport by one playlist page
- `shift+up` / `shift+down`: reorder selection up/down
- `v`: toggle selection for the current row
- `delete`: remove selected tracks (confirm)
- `a`: open/toggle the Actions menu (Add files/folder, clear, metadata actions)
- `f`: focus the Find input
- `enter` (in Find): return focus to playlist
- `space`: play/pause
- `n` / `p`: next/previous track
- `x`: stop
- `left` / `right`: seek -5s / +5s
- `shift+left` / `shift+right`: seek -30s / +30s
- `home` / `end`: seek to start/end
- `-` / `+`: volume down/up
- `shift+-` / `shift+=`: volume down/up by 10
- `[` / `]`: speed down/up
- `\`: speed reset to 1.0
- `r`: cycle repeat mode
- `s`: toggle shuffle
- `z`: cycle visualizer plugin
- `escape`: dismiss modal/popup; in Find it clears query and exits Find mode

Built-in visualizer IDs include:
- `basic`
- `matrix.green`, `matrix.blue`, `matrix.red`
- `ops.hackscope`
- `vu.reactive`
- `viz.spectrogram.waterfall`
- `viz.spectrum.terrain`
- `viz.reactor.particles`
- `viz.particle.gravity_well`
- `viz.spectrum.radial`
- `viz.typography.glitch`
- `viz.waveform.proxy`
- `viz.waveform.neon`
- `cover.ascii.static`, `cover.ascii.motion` (embedded artwork ASCII; requires embedded cover art in media files)
  - Fallback lookup is local-only and also checks sidecar files in the same directory (`cover.*`, `folder.*`, `front.*`, `album.*`, `artwork.*`, `<track-stem>.*`).

Lazy analysis cache notes:
- Scalar level, FFT/spectrum, waveform-proxy, and beat analysis are computed only when requested by visualizer flows.
- Computed analysis is persisted in SQLite cache and reused across restarts.
- Visualizers may expose analysis state labels such as `READY`, `LOADING`, or `MISSING` while cache fills.

Large-playlist guidance:
- `tz-player` is designed to handle high-count playlists (for example ~100k rows), but behavior depends on terminal throughput and host storage performance.
- Keep logs enabled (`INFO` default) when tuning large libraries; slow DB hotspots emit `event=playlist_store_slow_query` entries with operation and elapsed ms.
- Find/search uses an SQLite FTS-backed path when available and falls back to LIKE matching on SQLite builds without FTS5 support.
- FTS mode generally scales better for broad and multi-token queries; fallback mode is compatible but can be slower at very high counts.
- Search operations include a `mode` field in slow-query logs (`fts` or `like_fallback`) to help diagnose performance behavior.
- Find/search and metadata-heavy views are the most expensive paths; narrow search terms and allow lazy analysis to warm over time.
- Prefer SSD-backed app data directories for best playlist/query responsiveness.
- For benchmark-style checks, run opt-in perf tests:
  - `TZ_PLAYER_RUN_PERF=1 .ubuntu-venv/bin/python -m pytest tests/test_performance_opt_in.py`

Drop-in local plugin folder:
- `tz-player` always scans the user plugin folder:
  - `<user_config_dir>/visualizers/plugins`
- This folder is created automatically at startup.
- You can add additional plugin paths with `--visualizer-plugin-path`.

Status pane controls:
- Click or drag the TIME bar to seek.
- Click or drag the VOL and SPD bars to change volume and speed.
- Playback speed range is capped to `0.5x` through `4.0x` for backend compatibility.
- Time display shows MM:SS normally and switches to H:MM:SS for long tracks.

Current track information pane:
- Shows labeled metadata fields for `Title`, `Artist` (and `Genre` when available), `Album` + `Year`, and `Time` + `Bitrate` (when discoverable).

Playlist footer:
- Track counter shows `Track: ####/####` (current/total).
- Repeat indicator shows `R:OFF|ONE|ALL` and shuffle shows `S:OFF|ON`.
- Transport buttons allow Prev/Play/Pause/Stop/Next with mouse clicks.

Find/filter behavior:
- Typing in Find filters playlist rows by metadata/path text.
- Empty query restores the full playlist view.
- Escape priority is deterministic: popup/modal dismisses first, then Find exits/clears.
- Playback keys are available from main UI focus states (playlist pane, viewport, footer controls).

Add files picker:
- `Actions -> Add files...` opens a tree picker with drive/root navigation.
- Only supported audio files are listed.
- `space` toggles file selection, `enter` opens folders (or toggles file), and `ctrl+s` confirms selected files.

Add folder picker:
- `Actions -> Add folder...` opens the same tree navigation modal in folder-selection mode.
- Only folders are selectable.
- `space` selects the highlighted folder and `ctrl+s` confirms it for recursive media scan/add.

## Troubleshooting

Startup failure contract:
- Fatal startup failures return non-zero exit code and print a remediation hint.
- In-app startup failures show a modal with:
  - what failed,
  - likely cause,
  - next step.
- Non-fatal runtime failures are surfaced in the status line as `Notice:` text (for example visualizer fallback or envelope fallback warnings).

Common failure cases:

1. VLC backend unavailable:
- Symptom: app cannot initialize VLC backend.
- Behavior: startup stops and shows an actionable error modal; process exits non-zero.
- Next step: install VLC/libVLC, verify runtime linkage/PATH, then run `tz-player doctor --backend vlc`.

5. Missing ffmpeg for non-WAV VU envelope analysis:
- Symptom: VU source stays in fallback mode for MP3/FLAC/OGG and visualizer shows an ffmpeg diagnostic notice.
- Behavior: playback is unaffected; visualization uses fallback levels.
- Next step: install ffmpeg and run `tz-player doctor` to confirm detection.

2. State file unreadable/corrupt:
- Symptom: startup warning/error about state load.
- Behavior: app recovers with defaults where possible.
- Next step: inspect state file under `<user_config_dir>/state.json`, then re-run with `--verbose`.

3. Database access/init failure:
- Symptom: startup fails during playlist store init.
- Behavior: startup error modal appears with DB-specific guidance (permissions/path/lock/corruption) and startup fails safely.
- Next step: verify permissions/path for `<user_data_dir>/tz-player.sqlite`; re-run with `--verbose`.

4. Missing media path:
- Symptom: add/play action fails for missing files.
- Behavior: app surfaces actionable error text and keeps UI responsive.
- Next step: verify file path exists and is readable; refresh metadata after fixing paths.
