# Visualizer Lifecycle Workflow

This document maps the visualizer workflow across app startup, registry/host setup, per-frame rendering, runtime switching, and teardown.

## 1. Scope

- Included:
  - CLI/runtime visualizer configuration (`--visualizer-fps`, `--visualizer-plugin-path`, `--visualizer-plugin-security`, `--visualizer-plugin-runtime`)
  - Startup initialization (`_start_visualizer`)
  - Per-frame rendering (`_render_visualizer_frame`)
  - Runtime plugin switching (`action_cycle_visualizer`, key `z`)
  - Host fallback/throttling behavior
  - Shutdown path (`_stop_visualizer`)
- Excluded:
  - Internals of each specific visualizer’s artistic output
  - Detailed audio-envelope analysis workflow beyond what affects frame inputs

## 2. Entrypoints and Configuration

1. CLI parser accepts visualizer options:
- `src/tz_player/app.py:1258` `--visualizer-fps` (clamped 2..30)
- `src/tz_player/app.py:1263` `--visualizer-plugin-path` (repeatable)
- `src/tz_player/app.py` `--visualizer-plugin-security` (`off|warn|enforce`)
- `src/tz_player/app.py` `--visualizer-plugin-runtime` (`in-process|isolated`)

2. `main()` passes overrides into `TzPlayerApp(...)`:
- `src/tz_player/app.py:1288`

3. During `_initialize_state()`, effective runtime state is normalized and persisted:
- Visualizer FPS resolved from CLI override or persisted state
- Plugin paths resolved from CLI override or persisted state
- `src/tz_player/app.py:346`
- Persisted fields live in `AppState`:
  - `visualizer_id`, `visualizer_fps`, `visualizer_plugin_paths`
  - `src/tz_player/state_store.py:30`

## 3. Startup Initialization (`_start_visualizer`)

Called near end of app startup:

- `src/tz_player/app.py:409` -> `await self._start_visualizer()`

Flow:

1. Build registry:
- Always include default drop-in directory (`<user_config_dir>/visualizers/plugins`)
- Add persisted/CLI-configured plugin paths after default path
- Call `VisualizerRegistry.built_in(local_plugin_paths=..., plugin_security_mode=..., plugin_runtime_mode=...)`
- `src/tz_player/app.py:887`

2. Build host:
- `self.visualizer_host = VisualizerHost(self.visualizer_registry, target_fps=self.state.visualizer_fps)`
- Host clamps target FPS to `2..30`
- `src/tz_player/app.py:894`
- `src/tz_player/visualizers/host.py:28`

3. Activate initial plugin:
- Requested ID = persisted `state.visualizer_id` or registry default (`basic`)
- `active = self.visualizer_host.activate(requested, context)`
- If active ID changed (fallback/missing), persist updated `state.visualizer_id`
- `src/tz_player/app.py:901`

4. Start rendering:
- Render one immediate frame
- Install repeating timer with `set_interval(1.0 / target_fps, self._render_visualizer_frame)`
- `src/tz_player/app.py:906`

## 4. Registry Discovery and Plugin Contract

Registry responsibilities:

- Assemble built-ins plus optional local plugins
- Validate plugin IDs and deduplicate
- Provide factory creation by `plugin_id`
- `src/tz_player/visualizers/registry.py:31`

Built-ins include:

- `basic`
- `matrix.*`
- `ops.hackscope`
- `vu.reactive`
- `cover.ascii.*`
- `src/tz_player/visualizers/registry.py:64`

Local discovery supports:

- Python file paths
- Directory paths (all `.py`, excluding underscore-prefixed)
- Importable module/package paths
- `src/tz_player/visualizers/registry.py:110`

Plugin interface contract:

- `plugin_id`, `display_name`
- `on_activate(context)`, `on_deactivate()`, `render(frame) -> str`
- `src/tz_player/visualizers/base.py:46`

## 5. Per-Frame Render Path (`_render_visualizer_frame`)

Timer callback path:

1. Build `VisualizerFrameInput` from live app/player state:
- Layout size (`pane.size.width/height`)
- Playback transport state (`status`, `position`, `duration`, `volume`, `speed`, repeat/shuffle)
- Current track metadata (`path`, `title`, `artist`, `album`)
- Audio levels (`level_left`, `level_right`, `level_source`)
- `src/tz_player/app.py:929`

2. Call host:
- `output = self.visualizer_host.render_frame(frame, context)`
- `src/tz_player/app.py:957`

3. Surface host notices and diagnostics:
- Pull one-shot host notice (`consume_notice()`)
- Merge with audio-level notice (for example ffmpeg unavailable fallback)
- Update visualizer pane using ANSI-capable text rendering
- `src/tz_player/app.py:962`

4. Safety net:
- If render call itself raises at app level, pane shows `Visualizer unavailable`
- `src/tz_player/app.py:958`

## 6. Runtime Switching (`z` / `action_cycle_visualizer`)

1. Keyboard binding:
- `z` -> `cycle_visualizer`
- `src/tz_player/app.py:263`

2. Action flow:
- Get sorted plugin IDs from registry
- Compute next ID after current active ID (wraparound)
- Activate next plugin via host
- Persist new `state.visualizer_id`
- Render one immediate frame
- `src/tz_player/app.py:606`

3. Failure handling:
- If activation fails unexpectedly, app logs and shows an error modal
- `src/tz_player/app.py:624`

## 7. Host Fallback and Throttling Policy

`VisualizerHost` behavior:

1. Missing plugin on activate:
- Falls back to default plugin, emits notice
- `src/tz_player/visualizers/host.py:44`

2. Activation exception:
- Falls back to default plugin, emits notice
- `src/tz_player/visualizers/host.py:69`

3. Render exception:
- Marks failing plugin, activates default plugin, retries render
- Emits notice about fallback
- `src/tz_player/visualizers/host.py:136`

4. Performance throttling:
- Tracks frame budget from target FPS
- If render overruns budget 3 consecutive times, skips one frame (`"Visualizer throttled"`)
- `src/tz_player/visualizers/host.py:156`

## 8. Audio Level Data Feeding Visualizers

Visualizer frame levels come from `PlayerState`:

- `PlayerService._poll_position()` samples level source via `AudioLevelService.sample(...)`
- Updates `level_left/right/source` in state and emits `PlayerStateChanged`
- `src/tz_player/services/player_service.py:690`
- `src/tz_player/services/player_service.py:730`

App then forwards these values into each `VisualizerFrameInput`.

## 9. Shutdown Path

On app unmount:

1. Stop visualizer timer
2. Shutdown host (best-effort plugin deactivation)
3. Clear host reference

- `src/tz_player/app.py:421`
- `src/tz_player/app.py:912`
- `src/tz_player/visualizers/host.py:109`

## 10. Practical Notes

- Visualizer selection persists (`state.visualizer_id`), so fallback can rewrite persisted ID to a valid plugin.
- Frame cadence is bounded even if persisted/CLI values are out of range.
- Host-level notices are intentionally one-shot (`consume_notice`) and surfaced as transient runtime notices by the app.
