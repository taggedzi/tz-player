# ADR-0001 - Incremental Stabilization Over Rewrite

- Status: Accepted
- Date: 2026-02-13
- Deciders: Project owner and implementation agent

## Context

The project has meaningful existing assets: Textual UI composition, playback backend abstraction, persistent store/state, and broad test coverage. The codebase has regressions and reliability issues, but not a fundamentally invalid architecture.

## Decision

Continue from the current repository and stabilize incrementally instead of starting a new project from scratch.

## Consequences

Positive:

- Preserves existing domain knowledge encoded in code and tests.
- Faster path to production readiness by fixing regressions directly.
- Avoids rewrite risk and duplicate defect reintroduction.

Negative:

- Requires disciplined cleanup of historical branch noise.
- Must prioritize regression triage before feature expansion.

## Alternatives Considered

- Full rewrite from new repository after drafting spec.

## Follow-up Work

- Define explicit product target in `SPEC.md`.
- Triage regressions against spec and fix in milestone order.
- Keep architectural changes documented via ADRs.

