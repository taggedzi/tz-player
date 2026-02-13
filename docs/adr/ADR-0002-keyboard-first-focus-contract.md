# ADR-0002 - Keyboard-First Focus Contract

- Status: Accepted
- Date: 2026-02-13
- Deciders: Project owner and implementation agent

## Context

`tz-player` is intended as a keyboard-first TUI. Recent regressions showed that focus can move into input widgets in ways that prevent expected playback/navigation keys from working, causing a keyboard trap.

## Decision

Adopt an explicit focus contract:

- Global playback/navigation keys must remain reachable from primary UI states.
- Entering Find/Search mode must provide deterministic keyboard exit.
- Escape handling order is modal/pop-up first, then transient input/focus mode.
- No interaction may leave users unable to recover keyboard control.

## Consequences

Positive:

- Prevents recurrent keybinding regressions.
- Provides concrete acceptance criteria for UI behavior tests.
- Improves accessibility and user trust.

Negative:

- Requires additional focus-routing tests and maintenance.
- May constrain future widget-level key customization.

## Alternatives Considered

- Widget-local key handling without app-level focus contract.

## Follow-up Work

- Add focused regression tests for Find-focus enter/exit and global key routing.
- Ensure docs (`docs/usage.md`) match implemented keyboard behavior.
- Track unresolved focus traps as release blockers.

