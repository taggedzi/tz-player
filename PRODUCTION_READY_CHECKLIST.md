# Production Ready Checklist

Use this checklist before a release. Pick the section that matches your project type.

## tz-player Status (2026-02-13)

Active profile: **TUI Apps**

Validation status:

- [x] `.ubuntu-venv/bin/python -m ruff check .`
- [x] `.ubuntu-venv/bin/python -m ruff format --check .`
- [x] `.ubuntu-venv/bin/python -m mypy src`
- [x] `.ubuntu-venv/bin/python -m pytest` (105 passed, 3 skipped)
- [x] `TZ_PLAYER_RUN_PERF=1 .ubuntu-venv/bin/python -m pytest tests/test_performance_opt_in.py` (2 passed)
- [ ] `TZ_PLAYER_TEST_VLC=1 .ubuntu-venv/bin/python -m pytest -q tests/test_vlc_backend.py` (fails in this environment: `libVLC` runtime unavailable)

Backlog status:

- [x] BL-001 through BL-009 complete on `spec-baseline` (see `docs/gap-analysis.md`).
- [x] Workflow acceptance checklist added (`docs/workflow-acceptance.md`) and linked from `SPEC.md`.

Known remaining release tasks:

- [x] Update version/changelog for the release candidate.
- [x] Verify CI runs the same gate commands on PR (`.github/workflows/ci.yml`).
- [x] Run VLC-specific smoke tests in an environment with `TZ_PLAYER_TEST_VLC=1` (see `docs/vlc-smoke-test.md`).
- [ ] Run manual app startup check with VLC backend: `python -m tz_player.app --backend vlc`.
- [ ] Re-run VLC backend smoke test in a VLC-enabled environment (`TZ_PLAYER_TEST_VLC=1`).
- [ ] Verify release artifacts do not bundle external media binaries (`ffmpeg`/`vlc`/`libvlc`) using commands in **Release Artifact Guardrail** below.

Deferred with rationale:

- VLC-specific automated/manual checks are deferred until a host with VLC/libVLC installed is available.
- Deferral does not block non-VLC release quality gates; fallback-to-fake behavior is covered by automated tests.

## Release Artifact Guardrail (External Tooling Policy)

Policy: VLC/libVLC and FFmpeg are user-installed external tools and must not be bundled inside project release artifacts.

Run after building artifacts:

```bash
python -m pip install --upgrade build twine
python -m build
python -m twine check dist/*
```

Inspect wheel contents for suspicious bundled media/runtime binaries:

```bash
python -m zipfile -l dist/*.whl | rg -i "ffmpeg|libvlc|vlc\\.dll|libvlc\\.so|libvlc\\.dylib|avcodec|avformat|avutil|swresample|swscale"
```

Inspect sdist contents for suspicious bundled media/runtime binaries:

```bash
tar -tf dist/*.tar.gz | rg -i "ffmpeg|libvlc|vlc\\.dll|libvlc\\.so|libvlc\\.dylib|avcodec|avformat|avutil|swresample|swscale"
```

Expected result:

- No matches from either command.

If there are matches:

- Treat as a release blocker until confirmed benign or removed.
- Document resolution in release notes/checklist notes.

False positive guidance:

- Text/docs references such as `docs/media-setup.md` or `docs/license-compliance.md` mentioning `ffmpeg`/`vlc` are expected.
- Only compiled binaries/shared libraries or vendor folders containing media runtime files violate policy.

## Libraries

### Must Have (Release Blockers)

- [ ] Packaging & metadata: `pyproject.toml` complete, version updated, classifiers correct
- [ ] Configuration: no secrets in code, config defaults documented, env vars validated
- [ ] Input validation: public API guards invalid inputs and types
- [ ] Logging & observability: logging enabled with debug toggle; no noisy default logs
- [ ] Error handling & UX: clear error messages, no raw tracebacks by default
- [ ] Security basics: dependency review, safe file handling, path traversal checks
- [ ] Testing: unit tests for core API, negative/edge cases covered
- [ ] CI: lint + typecheck + tests on PR
- [ ] Release readiness: changelog updated, version tagged, artifacts build cleanly
- [ ] Docs: README quickstart + usage + troubleshooting

### Should Have (Strongly Recommended)

- [ ] Packaging: `twine check` passes; wheels build for supported Python versions
- [ ] Configuration: config file strategy with precedence (env > config > defaults)
- [ ] Input validation: defensive boundaries for sizes, limits, and formats
- [ ] Logging: optional file logging for debugging
- [ ] Testing: minimal integration tests against real workflows
- [ ] Maintenance: support policy and Python version policy stated

### Nice to Have

- [ ] Performance: basic benchmarks or profiling notes for hot paths
- [ ] Release: signed artifacts and automated release notes
- [ ] Docs: API reference and more examples

## CLI Tools

### Must Have (Release Blockers)

- [ ] Packaging & metadata: console script entry point verified; `pipx` install works
- [ ] Configuration: env vars + config files documented; sane defaults
- [ ] Input validation: argument validation with helpful errors
- [ ] Logging & observability: `--verbose` or debug toggle; log file option
- [ ] Error handling & UX: exit codes defined; no stack traces unless debug
- [ ] Security basics: safe file handling, temp directories, dependency review
- [ ] Testing: unit tests + CLI integration smoke tests
- [ ] CI: lint + typecheck + tests on PR
- [ ] Release readiness: changelog updated, version tagged, build artifacts verified
- [ ] Docs: README quickstart, usage examples, troubleshooting

### Should Have (Strongly Recommended)

- [ ] Configuration: config precedence and migration path documented
- [ ] Logging: structured-ish logs (key/value fields) for automation
- [ ] Testing: error-path tests and deterministic fixtures
- [ ] Maintenance: support window for Python versions

### Nice to Have

- [ ] Performance: startup time measured for large invocations
- [ ] Release: signed artifacts and automated release notes
- [ ] Docs: manpage or shell completions

## Desktop GUI Tools

### Must Have (Release Blockers)

- [ ] Packaging & metadata: packaging plan documented (wheel, installer, or bundler)
- [ ] Configuration: user settings stored in a safe location with defaults
- [ ] Input validation: defensive parsing for files and user input
- [ ] Logging & observability: log file option and debug toggle
- [ ] Error handling & UX: user-friendly dialogs; graceful fallback paths
- [ ] Security basics: safe file handling, temp directories, dependency review
- [ ] Testing: smoke tests for startup and critical flows
- [ ] CI: lint + typecheck + tests on PR
- [ ] Release readiness: changelog updated, versioned builds verified
- [ ] Docs: README setup + troubleshooting

### Should Have (Strongly Recommended)

- [ ] Configuration: config migrations and defaults tested
- [ ] Logging: crash reports or diagnostic bundle path
- [ ] Testing: UI regression tests for core workflows
- [ ] Maintenance: support policy and OS compatibility statement

### Nice to Have

- [ ] Performance: startup and rendering benchmarks
- [ ] Release: signed installers
- [ ] Docs: onboarding guide and screenshots

## TUI Apps

### Must Have (Release Blockers)

- [ ] Packaging & metadata: console script entry point verified
- [ ] Configuration: defaults documented, env overrides validated
- [ ] Input validation: defensive parsing and boundary checks
- [ ] Logging & observability: `--verbose` toggle and optional log file
- [ ] Error handling & UX: graceful errors and clean exit on failures
- [ ] Security basics: safe file handling and dependency review
- [ ] Testing: terminal-size and keybinding smoke tests
- [ ] CI: lint + typecheck + tests on PR
- [ ] Release readiness: changelog updated, versioned builds verified
- [ ] Docs: README setup + usage

### Should Have (Strongly Recommended)

- [ ] Configuration: config precedence documented
- [ ] Logging: structured-ish logs for automation
- [ ] Testing: error-path tests and deterministic fixtures
- [ ] Maintenance: support policy and Python version policy

### Nice to Have

- [ ] Performance: redraw/refresh profiling
- [ ] Release: signed artifacts and automated release notes
- [ ] Docs: troubleshooting matrix for terminal environments
