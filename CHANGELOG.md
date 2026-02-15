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
