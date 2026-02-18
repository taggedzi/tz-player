# Internal Documentation Coverage Tracker

Tracks file-by-file progress for `DOC-001` in `TODO.md`.

Status values:
- `todo`
- `in_progress`
- `done`

## Root Project Files

- [ ] `todo` `pyproject.toml`
- [ ] `todo` `noxfile.py`
- [ ] `todo` `README.md`
- [ ] `todo` `CONTRIBUTING.md`

## Source Files (`src/`)

- [x] `done` `src/tz_player/__init__.py`
- [x] `done` `src/tz_player/app.py`
- [x] `done` `src/tz_player/cli.py`
- [ ] `todo` `src/tz_player/doctor.py`
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
- [ ] `todo` `src/tz_player/services/audio_envelope_analysis.py`
- [ ] `todo` `src/tz_player/services/audio_envelope_store.py`
- [ ] `todo` `src/tz_player/services/audio_level_service.py`
- [ ] `todo` `src/tz_player/services/audio_tags.py`
- [x] `done` `src/tz_player/services/fake_backend.py`
- [ ] `todo` `src/tz_player/services/metadata_service.py`
- [x] `done` `src/tz_player/services/playback_backend.py`
- [x] `done` `src/tz_player/services/player_service.py`
- [x] `done` `src/tz_player/services/playlist_store.py`
- [x] `done` `src/tz_player/services/vlc_backend.py`
- [x] `done` `src/tz_player/ui/__init__.py`
- [ ] `todo` `src/tz_player/ui/actions_menu.py`
- [x] `done` `src/tz_player/ui/playlist_pane.py`
- [x] `done` `src/tz_player/ui/playlist_viewport.py`
- [ ] `todo` `src/tz_player/ui/slider_bar.py`
- [ ] `todo` `src/tz_player/ui/status_pane.py`
- [ ] `todo` `src/tz_player/ui/text_button.py`
- [x] `done` `src/tz_player/ui/transport_controls.py`
- [ ] `todo` `src/tz_player/ui/modals/__init__.py`
- [ ] `todo` `src/tz_player/ui/modals/confirm.py`
- [ ] `todo` `src/tz_player/ui/modals/error.py`
- [ ] `todo` `src/tz_player/ui/modals/file_tree_picker.py`
- [ ] `todo` `src/tz_player/ui/modals/path_input.py`
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

- [ ] `todo` `tests/conftest.py`
- [ ] `todo` `tests/test_app_envelope_analysis.py`
- [ ] `todo` `tests/test_app_parser.py`
- [ ] `todo` `tests/test_app_speed_limits.py`
- [ ] `todo` `tests/test_audio_envelope_analysis.py`
- [ ] `todo` `tests/test_audio_envelope_store.py`
- [ ] `todo` `tests/test_audio_level_service.py`
- [ ] `todo` `tests/test_audio_tags.py`
- [ ] `todo` `tests/test_backend_selection.py`
- [ ] `todo` `tests/test_cli_parser.py`
- [ ] `todo` `tests/test_doctor.py`
- [ ] `todo` `tests/test_extract_changelog_release.py`
- [ ] `todo` `tests/test_focus_navigation_matrix.py`
- [ ] `todo` `tests/test_gui_parser.py`
- [ ] `todo` `tests/test_logging_config.py`
- [ ] `todo` `tests/test_metadata_debounce.py`
- [ ] `todo` `tests/test_metadata_service.py`
- [ ] `todo` `tests/test_non_blocking_paths.py`
- [ ] `todo` `tests/test_paths.py`
- [ ] `todo` `tests/test_performance_opt_in.py`
- [ ] `todo` `tests/test_player_service.py`
- [ ] `todo` `tests/test_playlist_editing_integration.py`
- [ ] `todo` `tests/test_playlist_store.py`
- [ ] `todo` `tests/test_playlist_viewport.py`
- [ ] `todo` `tests/test_release_prepare.py`
- [ ] `todo` `tests/test_runtime_config.py`
- [ ] `todo` `tests/test_slider_bar.py`
- [ ] `todo` `tests/test_smoke.py`
- [ ] `todo` `tests/test_startup_resilience.py`
- [ ] `todo` `tests/test_state_store.py`
- [ ] `todo` `tests/test_status_pane.py`
- [ ] `todo` `tests/test_time_format.py`
- [ ] `todo` `tests/test_track_info_panel.py`
- [ ] `todo` `tests/test_transport_controls.py`
- [ ] `todo` `tests/test_ui.py`
- [ ] `todo` `tests/test_visualizer_basic.py`
- [ ] `todo` `tests/test_visualizer_cover_ascii.py`
- [ ] `todo` `tests/test_visualizer_hackscope.py`
- [ ] `todo` `tests/test_visualizer_host.py`
- [ ] `todo` `tests/test_visualizer_matrix.py`
- [ ] `todo` `tests/test_visualizer_registry.py`
- [ ] `todo` `tests/test_visualizer_selection_integration.py`
- [ ] `todo` `tests/test_visualizer_vu.py`
- [ ] `todo` `tests/test_vlc_backend.py`
- [ ] `todo` `tests/test_vlc_backend_unit.py`

## Tooling Scripts (`tools/`)

- [ ] `todo` `tools/extract_changelog_release.py`
- [ ] `todo` `tools/py_tree.py`
- [ ] `todo` `tools/release.py`
- [ ] `todo` `tools/release.sh`
- [ ] `todo` `tools/release_prepare.py`
- [ ] `todo` `tools/tree_maker.py`
- [ ] `todo` `tools/vlc_smoke.py`
