# ADR-0009 Live Sample Stream Gate for True Waveform Visualizers

- Status: Accepted
- Date: 2026-02-20

## Context

`tz-player` now has lazy scalar, spectrum, and beat analysis services that satisfy current advanced visualizers. However, true oscilloscope and stereo Lissajous/phase-scope plugins require live time-domain sample windows that are not currently provided by playback backends or the visualizer frame contract.

Without a dedicated live-sample capability, any oscilloscope/Lissajous implementation would be a stylized approximation rather than a true waveform/phase renderer.

## Decision

1. Defer true oscilloscope and true stereo Lissajous visualizers for v1.
2. Treat these modes as blocked until a dedicated live-sample capability task is approved and implemented.
3. Continue allowing approximation modes that derive visuals from existing scalar/spectrum/beat fields, provided they are documented as approximations.
4. Keep plugin API version unchanged; no live-sample fields are added to `VisualizerFrameInput` in this phase.

## Reasoning

- Preserves current non-blocking guarantees and avoids backend-specific data coupling during v1 hardening.
- Prevents misleading contract drift where plugins might assume waveform-grade fidelity from non-waveform inputs.
- Keeps compatibility stable while leaving a clear path for a future contract extension.

## Consequences

### Positive

- Scope remains aligned with current architecture and shipped capabilities.
- Plugin authors have explicit expectations about what data is and is not available.
- Existing advanced visualizers remain reliable and deterministic under current data contracts.

### Tradeoffs

- True waveform and stereo phase visual effects remain unavailable in v1.
- Approximation-based modes may not satisfy users expecting signal-accurate oscilloscope behavior.

## Follow-up

- Define a new live-sample service proposal covering:
  - backend sample extraction model and compatibility matrix
  - frame contract extension for sample windows/metadata
  - capability flags for sample-demanding plugins
  - perf and observability budgets for high-FPS rendering workloads
