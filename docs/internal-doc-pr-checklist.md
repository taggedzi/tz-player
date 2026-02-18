# Internal Documentation PR Checklist

Prepared for `DOC-001J`.

## Coverage

- [x] `docs/internal-doc-coverage.md` shows no remaining `todo` entries.
- [x] `src/` documentation pass complete.
- [x] `tests/` documentation pass complete.
- [x] Tooling/config/documentation files in scope documented.

## Quality Gates

- [x] `.ubuntu-venv/bin/python -m ruff check .`
- [x] `.ubuntu-venv/bin/python -m ruff format --check .`
- [x] `.ubuntu-venv/bin/python -m mypy src`
- [x] `.ubuntu-venv/bin/python -m pytest`

## Reviewer Notes

- Changes are documentation-only (docstrings/comments/docs) with no intended behavior changes.
- Skipped tests are opt-in by design:
  - `tests/test_performance_opt_in.py` requires `TZ_PLAYER_RUN_PERF=1`
  - `tests/test_vlc_backend.py` requires `TZ_PLAYER_TEST_VLC=1`
