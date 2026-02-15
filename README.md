# tz-player

[![CI](https://github.com/taggedzi/tz-player/actions/workflows/ci.yml/badge.svg)](https://github.com/taggedzi/tz-player/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/tz-player.svg)](https://pypi.org/project/tz-player/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

TaggedZ's command line music player.

## Screenshots

![Cover Art Screenshot](/docs/images/tz-player_cover-ascii-art_screenshot.png)

![Hackscope Screenshot](/docs/images/tz-player_hackscope_screenshot.png)

![VU Meter Screenshot](/docs/images/tz-player_vu-meter_screenshot.png)

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```


```bash
tz-player
```


## Installation


```bash
pip install tz-player
```

## Media Backend Setup

`tz-player` can run with a fake backend out of the box. Real audio playback and advanced visual analysis need external media tools.

- VLC/libVLC: required for real playback with `--backend vlc`.
- FFmpeg: optional, used only for non-WAV precomputed VU envelope analysis.

Install guidance:

- `docs/usage.md` (runtime usage)
- `docs/media-setup.md` (platform install commands)

## Licensing and Compliance

- Project license: MIT (`LICENSE`)
- Third-party notices: `THIRD_PARTY_LICENSES.md`
- Compliance notes and distribution guidance: `docs/license-compliance.md`

Metadata extraction uses `tinytag` (MIT) to keep runtime licensing permissive.


## Generate From Template

If this project was created with Copier, update it later with:

```bash
copier update
```

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

```bash
python -m ruff check .
python -m ruff format --check .
python -m mypy src
python -m pytest
```


```bash
nox -s lint typecheck tests
nox -s local
```


## Release

- Manual release automation is in GitHub Actions: `.github/workflows/release.yml`.
- Version source of truth is `src/tz_player/version.py`.
- Full instructions (including optional signing setup): `docs/release-process.md`.
- Release checklist and quality notes: `PRODUCTION_READY_CHECKLIST.md`.

## Project Layout

- `src/tz_player/` package source
- `tests/` tests
- `docs/` lightweight docs and notes

## Keyboard and Focus Behavior

- `f` focuses Find.
- While Find is focused, text entry keys are handled by the input.
- `enter` in Find returns focus to the playlist pane.
- `escape` handling order:
  - closes active modal/popup first
  - then clears/exits Find mode
- Playback keys (`space`, `n`, `p`, `x`, seek/volume/speed/repeat/shuffle) are available from main UI focus states.

See `docs/usage.md` for the full key map.

## Workflow Acceptance

See `docs/workflow-acceptance.md` for the per-workflow acceptance checklist and mapped tests.

## Visualization Plugins

See `docs/visualizations.md` for visualization subsystem goals, plugin contract, and authoring guidance.

## Runtime Flags and Diagnostics

Common runtime flags:

- `--backend {fake,vlc}`: choose playback backend for this run.
- `--verbose`: enable debug logging.
- `--quiet`: warnings/errors only (`--quiet` overrides `--verbose`).
- `--log-file <path>`: write logs to an explicit path.
- `--visualizer-plugin-path <path_or_module>`: add local visualizer plugin discovery path/module (repeatable; CLI overrides persisted list for that run).

Behavior notes:

- If `--backend vlc` is selected but VLC/libVLC is unavailable, the app falls back to `fake` and shows a clear in-app error.
- Default log path when `--log-file` is not provided: `<user_data_dir>/logs/tz-player.log`.
- Fatal startup errors return non-zero exit code and print a remediation hint.
- Non-fatal runtime issues (for example visualizer fallback, missing ffmpeg envelope source) are surfaced in the status line as `Notice:` messages.

See `docs/usage.md` for full keybindings and troubleshooting guidance.
