# AGENTS.md

Operational guide for coding agents working in this repository.

If anything here conflicts with `SPEC.md`, `SPEC.md` is authoritative.

## 1. Mission

Help ship `tz-player` to a production-ready v1 by implementing behavior defined in `SPEC.md` with reliable tests and clear docs.

## 2. Decision Hierarchy

When guidance conflicts, follow this order:

1. `SPEC.md`
2. Accepted ADRs in `docs/adr/`
3. User request for the current task
4. Existing code and tests
5. This `AGENTS.md`

## 3. Non-Negotiable Engineering Rules

- Do not introduce keyboard trap states.
- Preserve keyboard-first operation across key workflows.
- Avoid blocking the Textual event loop with direct file/db/network calls.
- Keep destructive playlist actions confirmation-protected.
- Do not silently change persisted state schema without migration/testing.

## 4. Working Practices

- Make narrowly scoped changes.
- Prefer fixing regressions over broad rewrites.
- Keep behavior deterministic and testable.
- Add or update tests for every behavior change.
- Update docs when user-visible behavior changes.

## 5. Testing Expectations

Minimum local validation for behavior changes:

- `ruff check .`
- `ruff format --check .`
- `mypy src`
- `pytest`

If full suite is not run, state what was skipped and why.

## 6. ADR Policy

- ADRs live in `docs/adr/`.
- Create/update an ADR when changing:
  - keyboard/focus interaction contract
  - playback backend architecture
  - persistence schema or migration behavior
  - major UI state or event-routing model
- Never silently violate an accepted ADR.

## 7. Safe Change Boundaries

- Do not remove existing backends without approval.
- Do not add remote/network features in v1 scope.
- Do not add major dependencies without explicit rationale and approval.

## 8. Definition of Done for Agent Tasks

A task is complete when:

- It aligns with `SPEC.md`.
- Code is implemented and readable.
- Tests cover the intended behavior and pass for touched area.
- Relevant docs/ADRs are updated.
- Known risks and follow-ups are documented.

