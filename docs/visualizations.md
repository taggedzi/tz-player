# Visualizations

This document defines the v1 target behavior for the visualization subsystem and how to write visualization plugins.

If this file conflicts with `SPEC.md`, `SPEC.md` is authoritative.

## Goals

- Keep visualization optional and non-blocking.
- Allow switching among built-in and local plugins by stable ID.
- Keep plugin failures isolated from playback and playlist workflows.

## Host Model

- Visualizer host renders into the right-side visualizer pane.
- Host owns plugin discovery, lifecycle, scheduling, fallback, and error handling.
- Plugins are pure render components from host-provided input to display text.

## Plugin Discovery

v1 target discovery order:

1. Built-in plugins under `tz_player.visualizers`.
2. Optional local plugins from configured import path(s).

Rules:

- Plugin IDs must be unique.
- Plugin IDs must be stable across releases.
- If duplicate IDs are found, host logs error and keeps the first valid plugin.

## Plugin Interface (Target)

```python
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class VisualizerContext:
    ansi_enabled: bool
    unicode_enabled: bool


@dataclass(frozen=True)
class VisualizerFrameInput:
    frame_index: int
    monotonic_s: float
    width: int
    height: int
    status: str  # idle|playing|paused|stopped
    position_s: float
    duration_s: float | None
    volume: float
    speed: float
    repeat_mode: str
    shuffle: bool
    track_id: int | None
    track_path: str | None
    title: str | None
    artist: str | None
    album: str | None


class VisualizerPlugin(Protocol):
    plugin_id: str
    display_name: str

    def on_activate(self, context: VisualizerContext) -> None: ...
    def on_deactivate(self) -> None: ...
    def render(self, frame: VisualizerFrameInput) -> str: ...
```

Notes:
- `render` output must be safe for Textual `Static` content.
- `render` should be deterministic for the same `VisualizerFrameInput`.
- No blocking file/db/network calls in `on_activate` or `render`.

## Lifecycle and Error Handling

- Host calls `on_activate` when a plugin is selected.
- Host calls `render` every scheduled frame.
- Host calls `on_deactivate` before plugin switch or shutdown.
- If `on_activate` or `render` raises, host logs error and switches to fallback plugin (`basic`).
- Failure message should include plugin ID and failure phase.

## Scheduling and Performance

- Default target cadence: 10 FPS.
- Configurable range: 2-30 FPS.
- Host may throttle slow plugins and log overruns.
- Plugins should avoid per-frame allocation spikes and expensive parsing.

## State and Persistence

- Selected plugin ID persists to `AppState.visualizer_id`.
- Unknown/missing persisted plugin falls back to `basic` on startup.
- Plugin-specific config should be namespaced by plugin ID if added later.

## Writing a Plugin

Checklist:

1. Define `plugin_id` and `display_name`.
2. Implement `on_activate`, `on_deactivate`, and `render`.
3. Return bounded-width/height text for the current pane dimensions.
4. Handle `idle`, `paused`, and missing-duration states explicitly.
5. Register plugin in the visualizer registry.
6. Add tests for activation, rendering, and fallback behavior.

Minimal example:

```python
from dataclasses import dataclass


@dataclass
class BasicBarsPlugin:
    plugin_id: str = "bars.basic"
    display_name: str = "Bars (Basic)"
    _ansi_enabled: bool = True

    def on_activate(self, context) -> None:
        self._ansi_enabled = context.ansi_enabled

    def on_deactivate(self) -> None:
        return None

    def render(self, frame) -> str:
        if frame.width <= 0 or frame.height <= 0:
            return ""
        if frame.status != "playing":
            return "Paused" if frame.status == "paused" else "Idle"
        progress = 0.0
        if frame.duration_s and frame.duration_s > 0:
            progress = min(max(frame.position_s / frame.duration_s, 0.0), 1.0)
        bars = int(progress * max(frame.width - 2, 1))
        return "[" + ("#" * bars).ljust(max(frame.width - 2, 1), "-") + "]"
```

## Testing Expectations

- Unit tests for registry duplicate ID handling and default fallback.
- Unit tests for persisted `visualizer_id` resolution.
- Unit tests for plugin exceptions during activation/render.
- UI integration test proving visualization failures do not block keyboard transport controls.

## Planned Plugin Pack (Next Phase)

This section documents planned extra-scope visualizers before implementation.

### 1) Matrix Rain (Non-Reactive)

- Goal: clean falling-code animation, independent of live audio levels.
- Implemented IDs:
  - `matrix.green`
  - `matrix.blue`
  - `matrix.red`
- Contract:
  - deterministic seeded motion for testability
  - bounded frame work per render
  - no blocking calls in `render`

### 2) Cyberpunk Terminal Ops (Fictional)

- Goal: movie-style fictional “target analysis” sequence keyed to current track metadata.
- Implemented ID:
  - `ops.cyberpunk`
- Runtime behavior:
  - Runs a queue of stage-specific prompt commands one at a time.
  - Each command has a fixed lifecycle: launch, active mini-game output, and result summary.
  - Active output is a text-mode simulation (for example defrag map, entropy pool fill, hash arena, mesh sweep), then completion text before advancing.
  - Output fills the available pane height and reflows safely on terminal resize.
- Planned stages:
  - surveillance
  - vulnerability scan
  - ICE break
  - account targeting
  - privilege escalation
  - data acquisition
  - decryption
  - transfer/download
  - log cleanup
- Safety/content constraints:
  - clearly fictional/non-operational
  - avoid actionable exploitation guidance
  - treat as stylized narrative output only

### 3) Audio-Reactive VU Meter

- Goal: level-based meter tied to real playback energy when signal data exists.
- Planned ID:
  - `vu.reactive`
- Contract:
  - consume normalized levels from backend/provider contract
  - smoothing and clipping to avoid jitter/spikes
  - graceful fallback when signal stream unavailable

## Implementation Prerequisites

- Add a level-signal provider contract for backend integrations.
- Keep fake backend deterministic for tests.
- Gate backend-specific signal features (for example VLC-only paths) behind capability checks.
- Maintain plugin fallback rules and non-blocking guarantees.
