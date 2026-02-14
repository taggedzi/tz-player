# tz-player

[![CI](https://github.com/taggedzi/tz-player/actions/workflows/ci.yml/badge.svg)](https://github.com/taggedzi/tz-player/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/tz-player.svg)](https://pypi.org/project/tz-player/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

TaggedZ's command line music player.

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

```bash
python -m pip install --upgrade build twine
python -m build
python -m twine check dist/*
```

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

Behavior notes:

- If `--backend vlc` is selected but VLC/libVLC is unavailable, the app falls back to `fake` and shows a clear in-app error.
- Default log path when `--log-file` is not provided: `<user_data_dir>/logs/tz-player.log`.
- Fatal startup errors return non-zero exit code and print a remediation hint.

See `docs/usage.md` for full keybindings and troubleshooting guidance.

## Release

See `PRODUCTION_READY_CHECKLIST.md` for a release checklist and recommendations.
