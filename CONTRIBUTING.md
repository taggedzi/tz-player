# Contributing

Thanks for considering a contribution.

## Maintainer Orientation

- `SPEC.md` is the behavior source of truth; `TODO.md` tracks execution state.
- `src/tz_player/app.py` is the integration point for UI, services, persistence, and visualizers.
- `src/tz_player/services/` owns transport, metadata, envelope, and storage logic.
- `src/tz_player/ui/` should stay keyboard-first and avoid focus traps.
- `src/tz_player/db/schema.py` changes require migration-safe updates and tests.
- Prefer `run_blocking(...)` for blocking file/DB/media work to protect Textual loop responsiveness.

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
- Mention any persistence schema or keyboard/focus contract changes explicitly.

## Binary Assets and `.gitattributes`

- Keep binary file patterns (for example `*.png`, `*.jpg`, `*.jpeg`, `*.gif`, `*.webp`) marked as `binary` in `.gitattributes`.
- Do not use blanket text normalization rules that force binary files to `text`, as this can corrupt images in git history.
