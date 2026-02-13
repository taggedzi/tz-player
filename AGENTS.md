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

- `.ubuntu-venv/bin/python -m ruff check .`
- `.ubuntu-venv/bin/python -m ruff format --check .`
- `.ubuntu-venv/bin/python -m mypy src`
- `.ubuntu-venv/bin/python -m pytest`

Environment rule:

- In this repo, run Python tooling via `.ubuntu-venv/bin/python -m ...` so installed dependencies (for example `mutagen`) resolve consistently.

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

## 9. MCP Setup Verification

This project can use the `repo-interrogator` MCP server for repository interrogation.

Verification checklist:

- Confirm server is configured:
  - `codex mcp list`
  - Expect an enabled `repo-interrogator` entry.
- Confirm server command/args target this repo:
  - `codex mcp get repo-interrogator`
  - Expect `--repo-root /mnt/e/Home/Documents/Programming/tz-player`.
- If MCP config changed, restart the Codex session to reload server availability.
- Run a direct server smoke check if needed:
  - `printf '%s\n' '{"id":"req-1","method":"repo.status","params":{}}' | /mnt/e/Home/Documents/Programming/repomap/.venv/bin/repo-mcp --repo-root /mnt/e/Home/Documents/Programming/tz-player`
  - Expect JSON response with `"ok": true`.
