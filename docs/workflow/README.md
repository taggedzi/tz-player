# Workflow Docs

This directory captures implementation workflows as practical call-path maps.

## Purpose

- Help maintainers quickly understand runtime behavior.
- Reduce onboarding time for debugging and feature work.
- Keep process knowledge versioned with code.

## File Naming

Use lowercase kebab-case and end with `.md`.

Examples:

- `app-startup-lifecycle.md`
- `play-selected-track.md`
- `playlist-clear-flow.md`

## When to Add or Update

- Add a workflow doc for new major behavior paths.
- Update an existing workflow doc when control flow changes.
- Prefer extending existing docs over creating near-duplicates.

## Suggested Structure

Each workflow doc should include:

1. Scope: what path the doc covers.
2. Entrypoint(s): where execution starts.
3. Main flow: ordered steps and key method calls.
4. Async/background work: tasks/workers/timers involved.
5. Failure handling: how errors surface and recover.
6. Shutdown/cleanup: teardown behavior if relevant.
7. Notes: important distinctions and gotchas.

## Template

```md
# <Workflow Title>

Short statement of what this workflow covers.

## 1. Scope

- Included:
- Excluded:

## 2. Entrypoint(s)

- `<file>:<line>`: `<function/method>`

## 3. Main Flow

1. `<step>`
2. `<step>`
3. `<step>`

## 4. Async/Background Work

- `<task/timer/worker>`: `<what it does>`

## 5. Failure Handling

- `<failure class>` -> `<user-visible behavior>`

## 6. Shutdown/Cleanup

- `<cleanup step>`

## 7. Notes

- `<important distinction>`
```

## Current Workflow Docs

- `app-startup-lifecycle.md`
- `play-selected-track.md`
- `visualizer-lifecycle.md`
- `playback-transport-controls-lifecycle.md`
- `playback-time-volume-speed-lifecycle.md`
