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
| WF-01 Launch and recover state | Startup remains responsive and backend fallback is safe. | `tests/test_startup_resilience.py::test_startup_falls_back_to_fake_backend_when_vlc_fails`, `tests/test_startup_resilience.py::test_startup_shows_generic_init_error_when_backend_start_fails`, `tests/test_startup_resilience.py::test_startup_shows_generic_error_when_db_init_fails`, `tests/test_startup_resilience.py::test_classify_db_startup_failure_permission_denied_message`, `tests/test_backend_selection.py` |
| WF-02 Navigate playlist | Cursor and scroll behavior are deterministic across focus states. | `tests/test_focus_navigation_matrix.py::test_key_routing_matrix_across_focus_targets`, `tests/test_ui.py::test_playlist_cursor_pins_on_scroll` |
| WF-03 Playback control | Declared playback keys route correctly from main UI focus states and status reflects state updates. | `tests/test_focus_navigation_matrix.py::test_key_routing_matrix_across_focus_targets`, `tests/test_ui.py::test_status_pane_updates`, `tests/test_ui.py::test_status_pane_runtime_notice_is_visible_and_clearable`, `tests/test_transport_controls.py::test_transport_controls_play_button_mouse_click`, `tests/test_slider_bar.py::test_slider_bar_mouse_drag_emits_progress_and_final` |
| WF-04 Find/search focus behavior | Find focus/filter is deterministic and recoverable by keyboard. | `tests/test_ui.py::test_find_filters_playlist_and_escape_resets`, `tests/test_ui.py::test_escape_exits_find_and_restores_global_keys`, `tests/test_focus_navigation_matrix.py::test_escape_priority_popup_then_find`, `tests/test_playlist_store.py::test_search_item_ids_and_fetch_by_item_ids` |
| WF-05 Playlist editing | Reorder/remove/add/clear remain synchronized between DB and UI with confirmation guards. | `tests/test_playlist_editing_integration.py::test_keyboard_reorder_selected_item`, `tests/test_playlist_editing_integration.py::test_remove_selected_respects_confirm_and_cancel`, `tests/test_playlist_editing_integration.py::test_add_files_action_parses_paths_and_updates_playlist`, `tests/test_ui.py::test_clear_playlist_action_resets_state`, `tests/test_playlist_store.py` |
| WF-06 Visualization rendering and selection | Visualizer selection persists safely and failures degrade to fallback behavior. | `tests/test_visualizer_host.py::test_activate_unknown_visualizer_falls_back_to_default`, `tests/test_visualizer_host.py::test_render_failure_falls_back_to_default`, `tests/test_visualizer_host.py::test_render_failure_logs_fallback_transition`, `tests/test_visualizer_host.py::test_active_requires_spectrum_reflects_plugin_capability`, `tests/test_visualizer_host.py::test_active_requires_beat_reflects_plugin_capability`, `tests/test_visualizer_registry.py::test_built_in_registry_includes_basic`, `tests/test_visualizer_registry.py::test_duplicate_plugin_id_keeps_first_factory`, `tests/test_visualizer_registry.py::test_registry_logs_load_summary`, `tests/test_visualizer_selection_integration.py::test_visualizer_selection_persists_across_restart`, `tests/test_visualizer_selection_integration.py::test_unknown_persisted_visualizer_falls_back_and_repersists`, `tests/test_visualizer_selection_integration.py::test_cli_visualizer_plugin_paths_override_persisted_state`, `tests/test_visualizer_selection_integration.py::test_app_beat_request_capability_follows_active_visualizer`, `tests/test_visualizer_hackscope.py::test_hackscope_plugin_is_registered_built_in`, `tests/test_visualizer_vu.py::test_vu_plugin_is_registered_built_in`, `tests/test_visualizer_vu.py::test_vu_plugin_declares_spectrum_requirement`, `tests/test_visualizer_vu.py::test_vu_render_shows_fft_ready_when_bands_available`, `tests/test_visualizer_waterfall.py::test_waterfall_plugin_is_registered_built_in`, `tests/test_visualizer_terrain.py::test_terrain_plugin_is_registered_built_in`, `tests/test_visualizer_reactor.py::test_reactor_plugin_is_registered_built_in`, `tests/test_visualizer_radial.py::test_radial_plugin_is_registered_built_in`, `tests/test_visualizer_typography.py::test_typography_plugin_is_registered_built_in`, `tests/test_spectrum_service.py::test_spectrum_service_returns_loading_and_schedules_on_cache_miss`, `tests/test_beat_service.py::test_beat_service_returns_loading_and_schedules_on_cache_miss`, `tests/test_player_service.py::test_player_service_sets_spectrum_state_when_enabled`, `tests/test_player_service.py::test_player_service_sets_beat_state_when_enabled`, `tests/test_app_envelope_analysis.py::test_missing_ffmpeg_sets_notice_and_warns_once`, `tests/test_app_envelope_analysis.py::test_wav_path_without_ffmpeg_keeps_notice_clear`, `tests/test_audio_envelope_analysis.py::test_requires_ffmpeg_for_envelope_by_extension` |
| WF-07 Configure runtime behavior and diagnostics | CLI/backend selection and persisted runtime state are deterministic and testable. | `tests/test_gui_parser.py`, `tests/test_gui_parser.py::test_gui_parser_accepts_repeatable_visualizer_plugin_paths`, `tests/test_backend_selection.py`, `tests/test_runtime_config.py`, `tests/test_logging_config.py`, `tests/test_logging_config.py::test_app_main_doctor_path_returns_report_exit_code`, `tests/test_logging_config.py::test_app_main_returns_nonzero_when_app_reports_startup_failed`, `tests/test_logging_config.py::test_gui_main_returns_nonzero_when_app_reports_startup_failed`, `tests/test_doctor.py`, `tests/test_app_parser.py`, `tests/test_app_parser.py::test_app_parser_accepts_repeatable_visualizer_plugin_paths`, `tests/test_startup_resilience.py::test_startup_falls_back_to_fake_backend_when_vlc_fails`, `tests/test_state_store.py` |

## Release Gate

Before a release candidate is considered production-ready:

1. Run the required validation commands.
2. Confirm no always-on acceptance test mapped above is skipped.
3. Document any temporary skip with owner and follow-up issue.
4. For environment-gated checks (for example VLC smoke coverage), document whether the gate was enabled for the release candidate.
