# tz-player

[![CI](https://github.com/OWNER/tz-player/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/tz-player/actions/workflows/ci.yml)
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
ruff check .
ruff format .
pytest
mypy src
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


## Release

See `PRODUCTION_READY_CHECKLIST.md` for a release checklist and recommendations.
