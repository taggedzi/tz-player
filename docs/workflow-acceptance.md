# Workflow Acceptance Checklist

This checklist maps each `SPEC.md` workflow to concrete automated tests.

## Required Validation Commands

Run from repository root:

```bash
.ubuntu-venv/bin/python -m ruff check .
.ubuntu-venv/bin/python -m ruff format --check .
.ubuntu-venv/bin/python -m mypy src
.ubuntu-venv/bin/python -m pytest
```

## Opt-in Performance Checks

Performance checks are intentionally opt-in and are excluded from default CI gating.

Run explicitly when profiling or before release sign-off:

```bash
TZ_PLAYER_RUN_PERF=1 .ubuntu-venv/bin/python -m pytest tests/test_performance_opt_in.py
```

## Workflow Coverage Matrix

| Workflow | Acceptance Intent | Automated Coverage |
| --- | --- | --- |
| WF-01 Launch and recover state | Startup remains responsive and backend fallback is safe. | `tests/test_startup_resilience.py::test_startup_falls_back_to_fake_backend_when_vlc_fails`, `tests/test_startup_resilience.py::test_startup_shows_generic_init_error_when_backend_start_fails`, `tests/test_backend_selection.py` |
| WF-02 Navigate playlist | Cursor and scroll behavior are deterministic across focus states. | `tests/test_focus_navigation_matrix.py::test_key_routing_matrix_across_focus_targets`, `tests/test_ui.py::test_playlist_cursor_pins_on_scroll` |
| WF-03 Playback control | Declared playback keys route correctly from main UI focus states and status reflects state updates. | `tests/test_focus_navigation_matrix.py::test_key_routing_matrix_across_focus_targets`, `tests/test_ui.py::test_status_pane_updates` |
| WF-04 Find/search focus behavior | Find focus/filter is deterministic and recoverable by keyboard. | `tests/test_ui.py::test_find_filters_playlist_and_escape_resets`, `tests/test_ui.py::test_escape_exits_find_and_restores_global_keys`, `tests/test_focus_navigation_matrix.py::test_escape_priority_popup_then_find`, `tests/test_playlist_store.py::test_search_item_ids_and_fetch_by_item_ids` |
| WF-05 Playlist editing | Reorder/remove/add/clear remain synchronized between DB and UI with confirmation guards. | `tests/test_playlist_editing_integration.py::test_keyboard_reorder_selected_item`, `tests/test_playlist_editing_integration.py::test_remove_selected_respects_confirm_and_cancel`, `tests/test_playlist_editing_integration.py::test_add_files_action_parses_paths_and_updates_playlist`, `tests/test_ui.py::test_clear_playlist_action_resets_state`, `tests/test_playlist_store.py` |
| WF-06 Visualization rendering and selection | Visualizer selection persists safely and failures degrade to fallback behavior. | `tests/test_state_store.py::test_state_roundtrip` (persisted `visualizer_id`), `tests/test_state_store.py::test_state_corrupt_json_defaults`; plugin host/fallback render tests are required before release sign-off. |
| WF-07 Configure runtime behavior and diagnostics | CLI/backend selection and persisted runtime state are deterministic and testable. | `tests/test_gui_parser.py`, `tests/test_backend_selection.py`, `tests/test_startup_resilience.py::test_startup_falls_back_to_fake_backend_when_vlc_fails`, `tests/test_state_store.py` |

## Release Gate

Before a release candidate is considered production-ready:

1. Run the required validation commands.
2. Confirm no always-on acceptance test mapped above is skipped.
3. Document any temporary skip with owner and follow-up issue.
4. For environment-gated checks (for example VLC smoke coverage), document whether the gate was enabled for the release candidate.
