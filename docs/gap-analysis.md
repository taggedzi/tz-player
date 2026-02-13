# Gap Analysis Against SPEC.md

Date: 2026-02-13  
Branch: `spec-baseline`

## Method

- Reviewed implementation and tests for each workflow in `SPEC.md`.
- Ran targeted runtime checks for known-risk areas (keyboard routing and metadata test behavior).
- Classified each workflow as:
  - `Met`
  - `Partial`
  - `Blocked`

## Workflow Mapping

### WF-01: Launch and recover state

Status: `Partial`

Evidence:
- Startup pipeline exists: `src/tz_player/app.py:184`
- State load/save used at startup: `src/tz_player/app.py:186`
- VLC fallback to fake backend exists with error modal: `src/tz_player/app.py:212`
- Playlist pane is focused after configure: `src/tz_player/app.py:245`
- Backend selection behavior is unit-tested: `tests/test_backend_selection.py:1`

Gaps:
- No startup watchdog/timeout; startup can still stall if dependency calls block indefinitely.
- No explicit test validating full startup fallback path end-to-end when VLC fails.

### WF-02: Navigate playlist

Status: `Partial`

Evidence:
- Up/down bindings on playlist pane: `src/tz_player/ui/playlist_pane.py:54`
- Deterministic cursor movement and row pinning behavior: `src/tz_player/ui/playlist_pane.py:356`
- Scroll mechanics and manual scrollbar events: `src/tz_player/ui/playlist_viewport.py:101`
- Cursor pin-on-scroll test exists: `tests/test_ui.py:207`

Gaps:
- Behavior depends on focus being in playlist context; no robust focus recovery contract enforcement.
- No integration test proving navigation remains stable after entering/leaving Find input.

### WF-03: Playback control

Status: `Partial`

Evidence:
- App-level playback keybindings: `src/tz_player/app.py:120`
- Playback action routing to `PlayerService`: `src/tz_player/app.py:264`
- Mouse transport controls wired: `src/tz_player/ui/transport_controls.py:49`
- Status pane updates from player state: `src/tz_player/ui/status_pane.py:70`

Gaps:
- Playback keybindings are blocked when Find input is focused (reproduced: `flags []` while focused `playlist-find`).
- No UI tests asserting keyboard playback routing in realistic focus states.

### WF-04: Find/search focus behavior

Status: `Blocked`

Evidence:
- `f` focuses find input: `src/tz_player/app.py:261`, `src/tz_player/ui/playlist_pane.py:152`
- Find input widget exists: `src/tz_player/ui/playlist_pane.py:86`
- No input change/submit handlers in current implementation (no search/filter path in pane).
- Escape only closes modal/popup in app handler: `src/tz_player/app.py:287`

Gaps:
- Typing in Find does not filter playlist (feature absent on this branch).
- No deterministic keyboard exit behavior for Find mode.
- Find focus can trap global controls in practice.
- `docs/usage.md` does not document Find exit behavior: `docs/usage.md:25`

### WF-05: Playlist editing

Status: `Partial`

Evidence:
- Reorder/select/remove/clear paths implemented: `src/tz_player/ui/playlist_pane.py:430`
- Destructive confirms for remove/clear: `src/tz_player/ui/playlist_pane.py:541`
- Clear playlist reset logic implemented: `src/tz_player/ui/playlist_pane.py:549`
- Clear reset behavior tested: `tests/test_ui.py:161`
- Store-level reorder/remove/duplicate behavior tested: `tests/test_playlist_store.py:18`

Gaps:
- Limited integration coverage for add-files/add-folder UI paths.
- Limited keyboard-focused tests for reorder and remove flows through real focus transitions.

## Cross-Cutting Quality Gate Gaps

1. Test reliability blocker  
Observed: `tests/test_metadata_service.py::test_metadata_service_fallback_and_duration` hangs in this environment and times out.  
File: `tests/test_metadata_service.py:27`

2. Keyboard/focus contract is not fully specified in code  
No explicit focus-state machine; behavior is distributed across app/pane/input event handlers.

3. Focus visibility is inconsistent  
Some controls have focus styling (`TextButton`), but viewport/input-focused states are not uniformly explicit in app CSS.  
Files: `src/tz_player/ui/text_button.py:17`, `src/tz_player/app.py:34`

## Prioritized Fix Backlog

### P0 (Release blockers)

1. `BL-001` Fix Find focus trap and define deterministic escape behavior  
Workflows: WF-03, WF-04  
Why now: Keyboard trap blocks primary controls.  
Proposed implementation:
- Implement explicit Find mode handlers (`Input.Changed`, `Input.Submitted`, `Escape`) in playlist pane.
- Add app-level escape order: modal/popup first, then Find exit/clear.
- Ensure playback keybindings remain reachable from main focus states.
Acceptance tests:
- New UI test: playback keys still work after entering/exiting Find focus.
- New UI test: escape exits Find mode deterministically.

2. `BL-002` Implement or remove search behavior ambiguity for v1  
Workflows: WF-04  
Why now: Spec says “Typing filters playlist (when enabled)” but branch currently has no filtering behavior.  
Decision required:
- Either implement filtering now (preferred), or explicitly scope it out in `SPEC.md`.
Acceptance tests:
- If enabled: query updates visible rows and reset on empty query.
- If deferred: spec/docs clearly state Find is focus-only placeholder.

3. `BL-003` Resolve metadata test hang and enforce timeout discipline  
Workflows: Quality gates  
Why now: `pytest` gate is not trustworthy with hanging test.  
Proposed implementation:
- Isolate root cause in `MetadataService`/test fixture interaction.
- Add bounded timeout strategy for metadata test path.
- Ensure CI cannot hang indefinitely on this test.
Acceptance tests:
- Targeted metadata tests complete under deterministic time budget.

### P1 (High value after blockers)

4. `BL-004` Add startup resilience checks and tests  
Workflows: WF-01  
Proposed implementation:
- Add integration test for VLC-fallback path in app initialization.
- Add startup failure-path assertions (error modal + usable UI).

5. `BL-005` Strengthen navigation/focus regression test suite  
Workflows: WF-02, WF-03, WF-04  
Proposed implementation:
- Add matrix tests across focus targets (`playlist-pane`, `playlist-viewport`, `playlist-find`, transport buttons).
- Verify up/down, play controls, and escape semantics per focus state.

6. `BL-006` Expand playlist editing integration tests  
Workflows: WF-05  
Proposed implementation:
- Add UI tests for reorder via keyboard, remove-selected confirm/cancel, and add-files path parsing behavior.

### P2 (Polish and maintainability)

7. `BL-007` Normalize focus styling for interactive widgets  
Workflows: UX contract  
Proposed implementation:
- Add explicit `:focus` styles for viewport/find and key controls to satisfy visible focus requirement.

8. `BL-008` Align docs with implemented keyboard/focus behavior  
Files: `docs/usage.md`, `README.md`  
Proposed implementation:
- Document final escape/find behavior and key routing model once stabilized.

9. `BL-009` Add per-workflow acceptance checklist to CI docs  
Proposed implementation:
- Track WF-01..WF-05 acceptance checks in a test plan document and link from `SPEC.md`.

## Recommended Execution Order

1. `BL-001` Find focus trap
2. `BL-003` metadata hang reliability
3. `BL-002` search behavior decision/implementation
4. `BL-004` startup resilience tests
5. `BL-005` focus/navigation regression matrix
6. `BL-006` playlist editing integration expansion
7. `BL-007` + `BL-008` + `BL-009` polish/documentation

