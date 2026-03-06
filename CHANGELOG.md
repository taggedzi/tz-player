# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- None.

### Changed

- None.

### Fixed

- None.


## [1.1.1] - 2026-03-06

### Added

- None.

### Changed

- Increase native helper timeout default

### Fixed

- Fix Windows helper artifact upload path
## [1.1.0] - 2026-03-06

### Added

- Add AI assistance notice
- Added binaries to gitignore file
- Add guided setup command and Windows helper

### Changed

- Update README badges
- Document VLC as required external dependency
- Lint fix
- Harden perf profiling artifacts
- Lint fix and Error fix for unit test
- Silence VLC logs by default
- Harden native helper limits and concurrency
- Document native helper default behavior
- Default native helper usage via state config
- Default helper build output to packaged path
- Rename native helper artifacts and docs
- Archive completed TODO items
- Document guided setup flow

### Fixed

- None.
## [1.0.3] - 2026-03-05

### Added

- None.

### Changed

- Release binary calls change

### Fixed

- None.
## [1.0.2] - 2026-03-05

### Added

- None.

### Changed

- Windows releated changes.

### Fixed

- Fixed import.
- Fix release path
## [1.0.1] - 2026-03-05

### Added

- None.

### Changed

- Lint Fix
- Updated Release process.
- Explicitly disable bundled native helper during release test step
- Make bundled native helper opt-in to keep default python path
- Harden local release scripts and expand recovery runbook

### Fixed

- Fix release staging lookup for downloaded native helper artifacts
## [1.0.0] - 2026-03-05

### Added

- Add GitHub follow-up commands after tag push
- Add packaged native helper binaries to release flow
- Add native analysis helper CLI POC and perf workflows
- Add bundle timing breakdown and precompute spectrum coefficients
- Add open option for perf HTML reports
- Add HTML perf suite report generator
- Add suite-level perf comparison tool
- Add local-corpus user-feel perf suite orchestration
- Add reusable captured-event summary extraction
- Add hidden hotspot frame marshaling benchmark
- Add perf benchmark runner for persistent artifacts
- Add hidden hotspot state-save and logging benchmark
- Add perf event context summaries for benchmark correlation
- Add reusable perf event wait and match helpers
- Add real cold-warm analysis cache benchmark artifact
- Add optional cProfile deep profiling mode
- Add perf benchmark runbook and local results dir
- Add resource trend capture for perf benchmarks
- Add hidden hotspot call-probe perf sweep
- Add opt-in DB query benchmark artifact and event correlation
- Add opt-in visualizer matrix benchmark artifact run
- Add opt-in controls latency jitter benchmark
- Add opt-in track switch preload benchmark scenario
- Add perf event capture hooks for benchmarks
- Add perf result artifact and comparison tooling
- Add local perf media corpus discovery helpers
- Add perf benchmark result schema contract
- Add plasma stream particle plugin
- Add data core fragmentation plugin
- Add constellation particle plugin
- Add audio tornado particle plugin
- Add magnetic grid particle plugin
- Add ember field particle plugin
- Add orbital system particle plugin
- Add reactive particle rain plugin
- Add shockwave rings particle plugin
- Start particle suite with gravity well plugin
- Add colorful waveform neon proxy visualizer
- Add waveform-proxy lazy cache pipeline
- Add responsiveness and throttle events
- Tune VU smoothing responsiveness
- Tune analysis cadence by responsiveness profile
- Add visualizer responsiveness profiles
- Add radial spectrum plugin
- Add particle reactor plugin
- Add audio terrain plugin
- Add typography glitch plugin
- Add spectrogram waterfall plugin
- Add lazy beat analysis cache and runtime wiring
- Add schema v5 FTS migration with fallback query path
- Harden store observability and random selection
- Added db storage of fft, and transitioned levels as well.
- Add isolated local plugin runtime mode
- Added vizualizer pluggin enhancement.
- Add: Added Screenshots to the README.md

### Changed

- Lint Fix
- Clarify release process and GitHub follow-up steps
- Clarify release flow: local single-command plus GitHub build follow-up
- Iint changes.
- More fixes.
- Build fixes.
- Reduce spectrum loop allocations and fix perf elapsed accounting
- Use 10 varied local tracks in corpus perf scenarios
- Use monotonic timestamps for perf event latency
- Changes for local music files for testing.
- Updated Git ignore for local performance testing files.
- Improve analysis caching and shared decode pipeline
- Improve async responsiveness and reduce UI blocking across audio/db/visualizers
- Async and IO todo plan.
- Todo update.
- Archive completed backlog and defer T-045
- Add waveform-proxy cache implementation tasks
- Add profile responsiveness validation matrix
- Preserve T-046 responsiveness tuning tasks
- Finalize oscilloscope/lissajous feasibility gate
- Add advanced pack reliability and perf checks
- Update contract and built-in plugin guidance
- Add ADR and beat contract/cache guidance
- Cover beat analysis store service and plugin gating
- Add ADR-0007 and complete T-042 guidance
- Extend opt-in large-playlist search perf scenarios
- Cover schema v5 migration and search index sync behavior
- Document large-playlist guidance and track T-041
- Add 100k playlist store opt-in benchmark checks
- Debug(ci): ruff version display.
- Document isolated runtime and complete T-038E
- Added support expectations.
- Added workflow documents.
- Mark DOC-001 complete after PR merge
- Mark DOC-001J blocked pending gh CLI
- Complete remaining source docs and PR checklist
- Add maintainer orientation and code map
- Document config and release tooling rationale
- Complete remaining test file documentation
- Document integration and async helper patterns
- Document shared fixtures and helper stubs
- Document utility and cross-cutting modules
- Document plugin implementations and effects
- Document config helpers and visualizer core
- Document queue transport and persistence flow
- Document service and backend contracts
- Add coverage tracker and entrypoint docstrings
- Add internal documentation campaign tasks
- Updated production checklist and .gitignore
- Archived finished TODO items.
- Ui: add folder-mode tree picker for add-folder action
- Ui: replace add-files text modal with tree picker
- Playlist: add page up/down cursor navigation
- Ui: make tab-focused playlist controls visually explicit
- Ui: remove global focus outline that obscured text
- Ui: add universal focus outline for tab visibility
- Ui: strengthen focus visibility across interactive controls
- Docs(todo) updated with QOL features.
- Doc(readme): tried to make readme better targeted to audience and cleaner.
- Add binary assets gitattributes guidance
- Load tool module by path for cwd-agnostic import
- Review(tools/vlc_smoke.py): apply maintainer review findings
- Review(tools/tree_maker.py): apply maintainer review findings
- Review(tools/release_prepare.py): apply maintainer review findings
- Review(tools/release.py): apply maintainer review findings
- Review(tools/py_tree.py): apply maintainer review findings
- Review(tools/extract_changelog_release.py): apply maintainer review findings
- Review(tests/test_vlc_backend_unit.py): apply maintainer review findings
- Review(tests/test_vlc_backend.py): apply maintainer review findings
- Review(tests/test_visualizer_vu.py): apply maintainer review findings
- Review(tests/test_visualizer_selection_integration.py): apply maintainer review findings
- Review(tests/test_visualizer_registry.py): apply maintainer review findings
- Review(tests/test_visualizer_matrix.py): apply maintainer review findings
- Review(tests/test_visualizer_host.py): apply maintainer review findings
- Review(tests/test_visualizer_hackscope.py): apply maintainer review findings
- Review(tests/test_visualizer_cover_ascii.py): apply maintainer review findings
- Review(tests/test_ui.py): apply maintainer review findings
- Review(tests/test_transport_controls.py): apply maintainer review findings
- Review(tests/test_track_info_panel.py): apply maintainer review findings
- Review(tests/test_time_format.py): apply maintainer review findings
- Review(tests/test_status_pane.py): apply maintainer review findings
- Review(tests/test_state_store.py): apply maintainer review findings
- Review(tests/test_startup_resilience.py): apply maintainer review findings
- Review(tests/test_smoke.py): apply maintainer review findings
- Review(tests/test_slider_bar.py): apply maintainer review findings
- Review(tests/test_runtime_config.py): apply maintainer review findings
- Review(tests/test_release_prepare.py): apply maintainer review findings
- Review(tests/test_playlist_viewport.py): apply maintainer review findings
- Review(tests/test_playlist_store.py): apply maintainer review findings
- Review(tests/test_playlist_editing_integration.py): apply maintainer review findings
- Review(tests/test_player_service.py): apply maintainer review findings
- Review(tests/test_performance_opt_in.py): apply maintainer review findings
- Review(tests/test_paths.py): apply maintainer review findings
- Review(tests/test_non_blocking_paths.py): apply maintainer review findings
- Review(tests/test_metadata_service.py): apply maintainer review findings
- Review(tests/test_metadata_debounce.py): apply maintainer review findings
- Review(tests/test_logging_config.py): apply maintainer review findings
- Review(tests/test_gui_parser.py): apply maintainer review findings
- Review(tests/test_focus_navigation_matrix.py): apply maintainer review findings
- Review(tests/test_extract_changelog_release.py): apply maintainer review findings
- Review(tests/test_doctor.py): apply maintainer review findings
- Review(tests/test_backend_selection.py): apply maintainer review findings
- Review(tests/test_audio_tags.py): apply maintainer review findings
- Review(tests/test_audio_level_service.py): apply maintainer review findings
- Review(tests/test_audio_envelope_store.py): apply maintainer review findings
- Review(tests/test_audio_envelope_analysis.py): apply maintainer review findings
- Review(tests/test_app_speed_limits.py): apply maintainer review findings
- Review(tests/test_app_parser.py): apply maintainer review findings
- Review(tests/test_app_envelope_analysis.py): apply maintainer review findings
- Review(tests/conftest.py): apply maintainer review findings
- Review(src/tz_player/visualizers/vu.py): apply maintainer review findings
- Review(src/tz_player/visualizers/registry.py): apply maintainer review findings
- Review(src/tz_player/visualizers/matrix.py): apply maintainer review findings
- Review(src/tz_player/visualizers/host.py): apply maintainer review findings
- Review(hackscope): guard non-finite duration formatting
- Review(cover_ascii): validate cache max_entries
- Review(visualizer-basic): map error status explicitly
- Review(visualizers/base): pass with no code changes
- Review(visualizers/__init__): pass with no code changes
- Review(version): pass with no code changes
- Review(time_format): pass with no code changes
- Review(async_utils): validate callable input
- Review(utils/__init__): pass with no code changes
- Review(transport_controls): fail fast on unknown button action
- Review(text_button): fail fast on empty action
- Review(status_pane): remove dead duplicate spacer id
- Review(slider_bar): validate step and emit interval
- Review(playlist_viewport): guard drag move without capture
- Review(playlist_pane): validate add-folder path type
- Review(path_input_modal): submit on input enter
- Review(error_modal): add explicit close key actions
- Review(confirm_modal): add explicit keyboard actions
- Review(ui/modals/__init__): pass with no code changes
- Review(actions_menu): make dismiss idempotent
- Review(ui/__init__): pass with no code changes
- Review(state_store): reject bools in numeric coercion
- Review(vlc_backend): fail fast on thread lifecycle faults
- Review(playlist_store): fail fast on invalid move direction
- Review(player_service): harden duration handling
- Review(src/tz_player/services/playback_backend.py): apply maintainer review findings
- Review(src/tz_player/services/metadata_service.py): apply maintainer review findings
- Review(src/tz_player/services/fake_backend.py): apply maintainer review findings
- Review(src/tz_player/services/audio_tags.py): apply maintainer review findings
- Review(src/tz_player/services/audio_level_service.py): apply maintainer review findings
- Review(src/tz_player/services/audio_envelope_store.py): apply maintainer review findings
- Review(src/tz_player/services/audio_envelope_analysis.py): apply maintainer review findings
- Review(src/tz_player/services/__init__.py): apply maintainer review findings
- Review(src/tz_player/runtime_config.py): apply maintainer review findings
- Review(src/tz_player/paths.py): apply maintainer review findings
- Review(src/tz_player/logging_utils.py): apply maintainer review findings
- Review(src/tz_player/gui.py): apply maintainer review findings
- Review(src/tz_player/events.py): apply maintainer review findings
- Review(src/tz_player/doctor.py): apply maintainer review findings
- Review(src/tz_player/db/schema.py): apply maintainer review findings
- Review(src/tz_player/db/__init__.py): apply maintainer review findings
- Review(src/tz_player/cli.py): apply maintainer review findings
- Review(src/tz_player/app.py): apply maintainer review findings
- Review(src/tz_player/__init__.py): apply maintainer review findings
- Review(noxfile.py): apply maintainer review findings
- Review(tools/release.sh): apply maintainer review findings
- Review(Makefile): apply maintainer review findings
- Review(.pre-commit-config.yaml): apply maintainer review findings
- Review(repo_mcp.toml): apply maintainer review findings
- Review(pyproject.toml): apply maintainer review findings
- Updated todo to start code reviews.

### Fixed

- Fix cross-platform CI issues for native helper POC tests
- Fixes for tests, types, and syntax. General file clean up too.
- Fix perf tests using removed app visualizer field
- Fix perf runner pytest interpreter auto-detection
- Fix Python 3.9 event-loop error by lazy-initializing state persist lock
- Fixed version of ruff to prevent drift.
- Fix(ruff) fix.
- Syntax fix.
- Test fix.
- Default to vlc and fail startup when libVLC is unavailable
- Treat screenshots as binary assets
- Do not ffmpeg-fallback for wav decode failures
## [0.5.3] - 2026-02-14

### Added

- None.

### Changed

- Release: support auto-merge branch policies in release script
- Release: v0.5.2
- Release: process update.
- Release: add one-command local release orchestrator
- Release: make workflow tag-driven for protected branches
- Release: fixed bug.

### Fixed

- None.
## [0.5.2] - 2026-02-14

### Added

- Pre-release sweep results recorded in `PRODUCTION_READY_CHECKLIST.md`, including full validation gate and opt-in performance checks.
- Manual GitHub release automation (`.github/workflows/release.yml`) with version/changelog preparation, quality gates, artifact guardrail scan, optional signing, and release publishing.

### Changed

- Release-readiness tracking now explicitly documents deferred VLC-only checks when `libVLC` is unavailable in the current environment.
- Project version now has a single source of truth in `src/tz_player/version.py`, consumed by runtime and packaging metadata.
- Release: process update.
- Release: add one-command local release orchestrator
- Release: make workflow tag-driven for protected branches
- Release: fixed bug.

### Fixed

- None.
## [0.2.0rc1] - 2026-02-13

### Added

- Startup resilience integration tests for backend fallback and initialization failure paths.
- Focus/navigation regression matrix tests covering playlist, viewport, find, and footer focus states.
- Playlist editing integration tests for keyboard reorder, remove confirm/cancel, and add-files parsing.
- Workflow acceptance checklist mapping WF-01..WF-05 to automated tests in `docs/workflow-acceptance.md`.

### Changed

- Find/filter behavior now supports debounced text filtering with deterministic exit/clear behavior.
- CI gate commands now run via `python -m ...` for consistent tool resolution across environments.
- Documentation aligned with finalized keyboard/focus contract and escape priority semantics.

### Fixed

- Keyboard trap and focus-recovery regressions around Find input mode.
- Metadata test reliability issues by isolating blocking code paths and enforcing timeout discipline.
- Startup fallback path handling for VLC backend failures.
- Cross-environment typecheck reliability for optional `vlc` imports.
