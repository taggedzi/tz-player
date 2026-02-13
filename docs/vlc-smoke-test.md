# VLC Smoke Test Plan

Use this when preparing a release candidate in an environment with VLC installed.

## Prerequisites

- VLC/libVLC installed and discoverable by `python-vlc`.
- Test environment has audio output access.
- Repository dependencies installed:

```bash
python -m pip install -e ".[dev]"
```

## Smoke Commands

```bash
export TZ_PLAYER_TEST_VLC=1
python -m pytest -q tests/test_vlc_backend.py
```

## Manual Startup Fallback Check

1. Run app with VLC backend:

```bash
python -m tz_player.app --backend vlc
```

2. If VLC is unavailable, confirm:
- app remains responsive
- fallback error modal appears
- backend switches to fake

## Pass Criteria

- `tests/test_vlc_backend.py` passes when VLC is available.
- No hang/crash on startup with `--backend vlc`.
- Fallback behavior is graceful when VLC is unavailable.
