# Contributing

Thanks for considering a contribution.

## Development Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Checks

```bash
ruff check .
ruff format .
pytest
mypy src
```

## Pull Requests

- Keep changes focused and documented.
- Add or update tests when behavior changes.
- Update documentation when user-facing behavior changes.
