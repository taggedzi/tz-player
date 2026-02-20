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
2. Local drop-in plugins under `<user_config_dir>/visualizers/plugins`.
3. Optional local plugins from configured import path(s).

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
    level_left: float | None = None
    level_right: float | None = None
    level_source: str | None = None  # live|envelope|fallback
    level_status: str | None = None  # ready|loading|missing|error
    spectrum_bands: bytes | None = None
    spectrum_source: str | None = None  # cache|fallback
    spectrum_status: str | None = None  # ready|loading|missing|error
    waveform_min_left: float | None = None
    waveform_max_left: float | None = None
    waveform_min_right: float | None = None
    waveform_max_right: float | None = None
    waveform_source: str | None = None  # cache|fallback
    waveform_status: str | None = None  # ready|loading|missing|error
    beat_strength: float | None = None
    beat_is_onset: bool | None = None
    beat_bpm: float | None = None
    beat_source: str | None = None  # cache|fallback
    beat_status: str | None = None  # ready|loading|missing|error


class VisualizerPlugin(Protocol):
    plugin_id: str
    display_name: str
    plugin_api_version: int
    requires_spectrum: bool  # optional, defaults to False when omitted
    requires_beat: bool  # optional, defaults to False when omitted
    requires_waveform: bool  # optional, defaults to False when omitted

    def on_activate(self, context: VisualizerContext) -> None: ...
    def on_deactivate(self) -> None: ...
    def render(self, frame: VisualizerFrameInput) -> str: ...
```

Notes:
- `render` output must be safe for Textual `Static` content.
- `render` should be deterministic for the same `VisualizerFrameInput`.
- No blocking file/db/network calls in `on_activate` or `render`.
- `plugin_api_version` must match the app-supported plugin API version.
- Backward compatibility: plugins that do not define `requires_spectrum` and ignore new frame fields continue to work unchanged.
- Current contract choice: API version remains `1` and new fields are additive/optional.

## Lazy Analysis Contract

- Scalar levels and spectrum data are lazy and cache-backed.
- Beat detection data is also lazy and cache-backed.
- Analysis only computes when a visualizer path requests it.
- Once computed, analysis is persisted in SQLite cache and reused across restarts.
- `render` must treat `loading|missing|error` as normal states.
- `render` must never schedule blocking compute or DB work.
- Spectrum analysis scheduling is host-managed and keyed by plugin capability:
  - `requires_spectrum = True` opts in.
  - Omitted/False means no spectrum sampling work is triggered.
- Beat analysis scheduling is host-managed and keyed by plugin capability:
  - `requires_beat = True` opts in.
  - Omitted/False means no beat sampling work is triggered.
- Waveform-proxy analysis scheduling is host-managed and keyed by plugin capability:
  - `requires_waveform = True` opts in.
  - Omitted/False means no waveform-proxy sampling work is triggered.

## Built-In Visualizer IDs (Current)

- `basic`
- `matrix.green`
- `matrix.blue`
- `matrix.red`
- `ops.hackscope`
- `vu.reactive`
- `cover.ascii.static`
- `cover.ascii.motion`
- `viz.spectrogram.waterfall` (`requires_spectrum = True`)
- `viz.spectrum.terrain` (`requires_spectrum = True`)
- `viz.reactor.particles` (`requires_spectrum = True`, `requires_beat = True`)
- `viz.particle.gravity_well` (`requires_spectrum = True`, `requires_beat = True`)
- `viz.particle.shockwave_rings` (`requires_spectrum = True`, `requires_beat = True`)
- `viz.particle.rain_reactive` (`requires_spectrum = True`, `requires_beat = True`)
- `viz.spectrum.radial` (`requires_spectrum = True`, `requires_beat = True`)
- `viz.typography.glitch` (`requires_beat = True`)
- `viz.waveform.proxy` (`requires_waveform = True`)
- `viz.waveform.neon` (`requires_waveform = True`)

Fallback/capability semantics:
- Missing analysis data is expected during warmup and must render safely using state text such as `LOADING`, `MISSING`, or `ERROR`.
- Visualizers without capability flags continue to receive base frame fields and run unchanged.
- Capability flags only opt-in scheduler behavior; they do not guarantee immediate `ready` data on first frames.

## Oscilloscope / Lissajous Feasibility Gate

Current constraint summary:
- The current playback backend abstraction does not provide a guaranteed live time-domain sample stream for visualizers.
- The current visualizer frame contract does not provide stereo left/right sample vectors or explicit phase data.
- Existing lazy analysis services provide scalar levels, quantized FFT bands, and beat markers only.

Decision for v1:
- True oscilloscope and true stereo XY/Lissajous renderers are deferred.
- These variants are blocked until a dedicated live-sample capability is added to backend and frame contracts.

Practical fallback designs (supported now):
- Oscilloscope-style approximation:
  - derive a pseudo-wave from grouped FFT band envelopes plus scalar level
  - render persistence trails as stylized motion, clearly documented as non-waveform-accurate
- Lissajous-style approximation:
  - map low/mid grouped energies to X/Y trajectories
  - optionally use beat pulses to drive bloom/density changes
- Both fallback styles must preserve:
  - deterministic render output for same input frame
  - non-blocking render path
  - explicit handling of `loading|missing|error` analysis states

Live-sample expansion requirements (future task):
- Backend-facing service for bounded live sample chunks (mono and optional stereo variants).
- Contract extension for visualizer input fields carrying sample windows and sampling metadata.
- Capability flag(s) for sample-demanding plugins, with cache/fallback behavior defined.
- Perf/observability budgets to protect UI responsiveness under high refresh rates.

## Local Plugin Security Modes

- `off`: disable static preflight checks.
- `warn` (default): detect risky source patterns and allow load with warnings.
- `enforce`: detect risky source patterns and block plugin load.

Current static checks flag risky patterns such as:
- process/network primitives (`subprocess`, `socket`, `http`/`urllib`)
- dynamic execution (`exec`, `eval`, `compile`, `__import__`)
- destructive filesystem calls (`os.remove`, `shutil.rmtree`, write-mode `open(...)`)

These checks reduce risk but do not provide full sandboxing.

## Local Plugin Runtime Modes

- `in-process` (default): local plugins execute inside the app process.
- `isolated`: local plugins execute in a dedicated subprocess and are called over IPC.

`isolated` mode improves containment for plugin faults/hangs but is still not a full security sandbox.

## Trust Model and Limits

- Python plugins run as user-provided code and are not fully sandboxed in-process.
- Treat third-party plugins as trusted code unless reviewed.
- Use `enforce` mode to block plugins with obvious risky patterns, but do not treat it as complete containment.
- `isolated` mode provides process separation and timeout-based failover for local plugins.
- Stronger isolation still requires OS-level sandboxing and is not guaranteed by default runtime mode.

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
2. Set `plugin_api_version = 1` (current API).
3. Implement `on_activate`, `on_deactivate`, and `render`.
4. Return bounded-width/height text for the current pane dimensions.
5. Handle `idle`, `paused`, and missing-duration states explicitly.
6. If using scalar/spectrum analysis data, handle `loading|missing|error` explicitly.
7. Place plugin file/package in the drop-in folder or pass an explicit plugin path.
8. Add tests for activation, rendering, and fallback behavior.
9. Keep render-path work bounded: precompute constants, avoid large allocations, and avoid dynamic imports in `render`.

Minimal example:

```python
from dataclasses import dataclass


@dataclass
class BasicBarsPlugin:
    plugin_id: str = "bars.basic"
    display_name: str = "Bars (Basic)"
    plugin_api_version: int = 1
    # Optional capability flags default to False when omitted.
    requires_spectrum: bool = False
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

FFT-aware example sketch:

```python
class SpectrumBarsPlugin:
    plugin_id = "bars.spectrum"
    display_name = "Bars (Spectrum)"
    plugin_api_version = 1
    requires_spectrum = True

    def on_activate(self, context) -> None:
        self._ansi_enabled = context.ansi_enabled

    def on_deactivate(self) -> None:
        return None

    def render(self, frame) -> str:
        if frame.spectrum_status != "ready" or not frame.spectrum_bands:
            return f"FFT {frame.spectrum_status or 'missing'}"
        # Render cache-provided quantized uint8 bands.
        return " ".join(f"{value:03d}" for value in frame.spectrum_bands[:16])
```

Beat-aware example sketch:

```python
class BeatPulsePlugin:
    plugin_id = "pulse.beat"
    display_name = "Pulse (Beat)"
    plugin_api_version = 1
    requires_beat = True

    def on_activate(self, context) -> None:
        self._ansi_enabled = context.ansi_enabled

    def on_deactivate(self) -> None:
        return None

    def render(self, frame) -> str:
        if frame.beat_status != "ready":
            return f"BEAT {frame.beat_status or 'missing'}"
        return "PULSE!" if frame.beat_is_onset else "..."
```

Authoring patterns for scalar/FFT/beat:
- Scalar (`level_left`/`level_right`): treat missing values as normal; use deterministic fallback animation only if needed.
- FFT (`spectrum_bands`): prefer width-bucket aggregation to reduce jitter and keep CPU bounded.
- Waveform-proxy (`waveform_min_*`/`waveform_max_*`): treat as PCM-like envelope ranges, not true live sample vectors.
- Beat (`beat_is_onset`, `beat_strength`): use short accents (single-frame flash/pulse), not long blocking transitions.
- Never do DB reads, subprocess calls, filesystem scans, or network calls from `render`.

## Testing Expectations

- Unit tests for registry duplicate ID handling and default fallback.
- Unit tests for persisted `visualizer_id` resolution.
- Unit tests for plugin exceptions during activation/render.
- UI integration test proving visualization failures do not block keyboard transport controls.

## Plugin Pack Notes

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
  - `ops.hackscope`
- Runtime behavior:
  - `ops.hackscope` provides a staged HackScope screenplay flow (boot, ICE, map, defrag, scan, decrypt, extract, cover, dossier) with deterministic ambient overlay.
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
- Implemented ID:
  - `vu.reactive`

### 4) Advanced Analysis-Reactive Pack

- Implemented IDs:
  - `viz.spectrogram.waterfall`
  - `viz.spectrum.terrain`
  - `viz.reactor.particles`
  - `viz.spectrum.radial`
  - `viz.typography.glitch`
- Data capability model:
  - spectrum-only: waterfall, terrain
  - spectrum+beat: reactor, radial
  - beat-only: typography

### 5) Deferred True-Signal Modes

- Deferred modes:
  - true oscilloscope (time-domain waveform from live samples)
  - true stereo phase scope / Lissajous (left/right sample stream)
- Status:
  - blocked pending live-sample capability task and contract expansion
- Contract:
  - consume normalized levels from shared `AudioLevelService`
  - service source priority: `live backend` -> `envelope cache` -> `fallback`
  - opt in to lazy spectrum sampling with `requires_spectrum = True`
  - consume optional quantized spectrum bands with explicit `ready|loading|missing|error` handling
  - smoothing and clipping to avoid jitter/spikes
  - explicit source labeling in UI output (`LIVE`, `ENVELOPE`, `FALLBACK`)
  - graceful fallback when signal stream unavailable

### 4) Embedded Cover ASCII (Static + Motion)

- Goal: render embedded track artwork as ANSI-capable ASCII without blocking UI input.
- Implemented IDs:
  - `cover.ascii.static`
  - `cover.ascii.motion`
- Contract:
  - cover extraction and image decode run in a background executor and are cached by track fingerprint + pane size
  - source priority is local-only: embedded artwork tags -> sidecar image files in track directory (`cover.*`, `folder.*`, `front.*`, `album.*`, `artwork.*`, `<track-stem>.*`)
  - visualizers render placeholders while loading (`Loading artwork...`) and explicit fallback states (`No embedded/sidecar artwork`, `Artwork decode failed`)
  - static variant renders deterministic art for a given cached frame
  - motion variant applies deterministic wipe/slide transforms driven by `frame_index` while playing
  - both variants degrade safely when no track or no local artwork is available

## Implementation Prerequisites

- Add a level-signal provider contract for backend integrations.
- Add `AudioLevelService` with SQLite-backed envelope cache and source failover.
- Keep fake backend deterministic for tests.
- Gate backend-specific signal features (for example VLC-only paths) behind capability checks.
- Maintain plugin fallback rules and non-blocking guarantees.
