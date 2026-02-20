# ADR-0010 Librosa Spike Workflow and Licensing Guardrails

- Status: Accepted
- Date: 2026-02-20
- Technical Story: `T-050` (Librosa Beat-Analysis Spike Workflow)

## Context

Recent beat-detection and fireworks improvements significantly increased responsiveness, but beat onset alignment and strength quality are still under active tuning for music with strong rhythmic structure.

The project needs a safe way to evaluate a potentially higher-quality beat-analysis implementation (`librosa`) without risking loss of the current stable improvements.

Dependency and license constraints also matter: prior consideration of `aubio` was blocked by GPL-3.0 implications for an MIT-distributed project.

## Decision

1. Use a branch-isolated spike workflow for `librosa` evaluation:
   - baseline branch: `feat/beat-fireworks-diagnostics`
   - child spike branch: `feat/librosa-beat-spike`
2. Keep all `librosa` experimentation on the spike branch only until acceptance gates pass.
3. Use explicit merge/discard gates:
   - quality gates (`ruff`, format-check, `mypy`, `pytest`) pass
   - measurable beat/onset improvement on representative tracks
   - no regression to non-blocking scheduling/cache behavior
   - docs/license notes updated if dependency is retained
4. If gates fail, discard the spike branch and keep the baseline branch as the released path.

## Consequences

### Positive

- Protects current beat/fireworks gains from experimental churn.
- Enables rapid iteration with a clean rollback path.
- Keeps dependency/license decisions explicit and reviewable.

### Tradeoffs

- Short-term branch management overhead.
- Potential duplicate work if the spike is discarded.

## Alternatives Considered

- Experiment directly on the baseline branch.
  - Rejected: increases rollback risk and mixes stable + experimental changes.
- Adopt `aubio` directly.
  - Rejected for MIT distribution path due to GPL-3.0 license constraints.

## Follow-up Work

- Implement `T-050B` on `feat/librosa-beat-spike`.
- Execute `T-050C` A/B validation with beat scope diagnostics and representative tracks.
- Record final `merge` vs `discard` outcome and update docs accordingly.
