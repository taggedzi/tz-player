# Internal Documentation Coverage Tracker

Tracks file-by-file progress for `DOC-001` in `TODO.md`.

Status values:
- `todo`
- `in_progress`
- `done`

## Root Project Files

- [x] `done` `pyproject.toml`
- [x] `done` `noxfile.py`
- [x] `done` `README.md`
- [x] `done` `CONTRIBUTING.md`

## Source Files (`src/`)

- [x] `done` `src/tz_player/__init__.py`
- [x] `done` `src/tz_player/app.py`
- [x] `done` `src/tz_player/cli.py`
- [x] `done` `src/tz_player/doctor.py`
- [x] `done` `src/tz_player/events.py`
- [x] `done` `src/tz_player/gui.py`
- [x] `done` `src/tz_player/logging_utils.py`
- [x] `done` `src/tz_player/media_formats.py`
- [x] `done` `src/tz_player/paths.py`
- [x] `done` `src/tz_player/runtime_config.py`
- [x] `done` `src/tz_player/state_store.py`
- [x] `done` `src/tz_player/version.py`
- [x] `done` `src/tz_player/db/__init__.py`
- [x] `done` `src/tz_player/db/schema.py`
- [x] `done` `src/tz_player/services/__init__.py`
- [x] `done` `src/tz_player/services/audio_envelope_analysis.py`
- [x] `done` `src/tz_player/services/audio_envelope_store.py`
- [x] `done` `src/tz_player/services/audio_level_service.py`
- [x] `done` `src/tz_player/services/audio_tags.py`
- [x] `done` `src/tz_player/services/fake_backend.py`
- [x] `done` `src/tz_player/services/metadata_service.py`
- [x] `done` `src/tz_player/services/playback_backend.py`
- [x] `done` `src/tz_player/services/player_service.py`
- [x] `done` `src/tz_player/services/playlist_store.py`
- [x] `done` `src/tz_player/services/vlc_backend.py`
- [x] `done` `src/tz_player/ui/__init__.py`
- [x] `done` `src/tz_player/ui/actions_menu.py`
- [x] `done` `src/tz_player/ui/playlist_pane.py`
- [x] `done` `src/tz_player/ui/playlist_viewport.py`
- [x] `done` `src/tz_player/ui/slider_bar.py`
- [x] `done` `src/tz_player/ui/status_pane.py`
- [x] `done` `src/tz_player/ui/text_button.py`
- [x] `done` `src/tz_player/ui/transport_controls.py`
- [x] `done` `src/tz_player/ui/modals/__init__.py`
- [x] `done` `src/tz_player/ui/modals/confirm.py`
- [x] `done` `src/tz_player/ui/modals/error.py`
- [x] `done` `src/tz_player/ui/modals/file_tree_picker.py`
- [x] `done` `src/tz_player/ui/modals/path_input.py`
- [x] `done` `src/tz_player/utils/__init__.py`
- [x] `done` `src/tz_player/utils/async_utils.py`
- [x] `done` `src/tz_player/utils/time_format.py`
- [x] `done` `src/tz_player/visualizers/__init__.py`
- [x] `done` `src/tz_player/visualizers/base.py`
- [x] `done` `src/tz_player/visualizers/basic.py`
- [x] `done` `src/tz_player/visualizers/cover_ascii.py`
- [x] `done` `src/tz_player/visualizers/hackscope.py`
- [x] `done` `src/tz_player/visualizers/host.py`
- [x] `done` `src/tz_player/visualizers/matrix.py`
- [x] `done` `src/tz_player/visualizers/registry.py`
- [x] `done` `src/tz_player/visualizers/vu.py`

## Test Files (`tests/`)

- [x] `done` `tests/conftest.py`
- [x] `done` `tests/test_app_envelope_analysis.py`
- [x] `done` `tests/test_app_parser.py`
- [x] `done` `tests/test_app_speed_limits.py`
- [x] `done` `tests/test_audio_envelope_analysis.py`
- [x] `done` `tests/test_audio_envelope_store.py`
- [x] `done` `tests/test_audio_level_service.py`
- [x] `done` `tests/test_audio_tags.py`
- [x] `done` `tests/test_backend_selection.py`
- [x] `done` `tests/test_cli_parser.py`
- [x] `done` `tests/test_doctor.py`
- [x] `done` `tests/test_extract_changelog_release.py`
- [x] `done` `tests/test_focus_navigation_matrix.py`
- [x] `done` `tests/test_gui_parser.py`
- [x] `done` `tests/test_logging_config.py`
- [x] `done` `tests/test_metadata_debounce.py`
- [x] `done` `tests/test_metadata_service.py`
- [x] `done` `tests/test_non_blocking_paths.py`
- [x] `done` `tests/test_paths.py`
- [x] `done` `tests/test_performance_opt_in.py`
- [x] `done` `tests/test_player_service.py`
- [x] `done` `tests/test_playlist_editing_integration.py`
- [x] `done` `tests/test_playlist_store.py`
- [x] `done` `tests/test_playlist_viewport.py`
- [x] `done` `tests/test_release_prepare.py`
- [x] `done` `tests/test_runtime_config.py`
- [x] `done` `tests/test_slider_bar.py`
- [x] `done` `tests/test_smoke.py`
- [x] `done` `tests/test_startup_resilience.py`
- [x] `done` `tests/test_state_store.py`
- [x] `done` `tests/test_status_pane.py`
- [x] `done` `tests/test_time_format.py`
- [x] `done` `tests/test_track_info_panel.py`
- [x] `done` `tests/test_transport_controls.py`
- [x] `done` `tests/test_ui.py`
- [x] `done` `tests/test_visualizer_basic.py`
- [x] `done` `tests/test_visualizer_cover_ascii.py`
- [x] `done` `tests/test_visualizer_hackscope.py`
- [x] `done` `tests/test_visualizer_host.py`
- [x] `done` `tests/test_visualizer_matrix.py`
- [x] `done` `tests/test_visualizer_registry.py`
- [x] `done` `tests/test_visualizer_selection_integration.py`
- [x] `done` `tests/test_visualizer_vu.py`
- [x] `done` `tests/test_vlc_backend.py`
- [x] `done` `tests/test_vlc_backend_unit.py`

## Tooling Scripts (`tools/`)

- [x] `done` `tools/extract_changelog_release.py`
- [x] `done` `tools/py_tree.py`
- [x] `done` `tools/release.py`
- [x] `done` `tools/release.sh`
- [x] `done` `tools/release_prepare.py`
- [x] `done` `tools/tree_maker.py`
- [x] `done` `tools/vlc_smoke.py`
