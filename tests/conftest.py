"""Test configuration."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import tz_player.app as app_module  # noqa: E402
import tz_player.services.metadata_service as metadata_service_module  # noqa: E402
import tz_player.services.playlist_store as playlist_store_module  # noqa: E402
import tz_player.ui.playlist_pane as playlist_pane_module  # noqa: E402


@pytest.fixture(autouse=True)
def run_blocking_inline(monkeypatch: pytest.MonkeyPatch):
    """Run blocking adapters inline in tests to avoid thread hangs in CI/sandbox."""

    async def _inline(func, /, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(playlist_store_module, "run_blocking", _inline)
    monkeypatch.setattr(metadata_service_module, "run_blocking", _inline)
    monkeypatch.setattr(app_module, "run_blocking", _inline)
    monkeypatch.setattr(playlist_pane_module, "run_blocking", _inline)


@pytest.fixture(autouse=True)
def ensure_current_event_loop():
    """Provide a current event loop for sync tests (required on Python 3.9)."""
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        yield
    finally:
        loop.close()
        asyncio.set_event_loop(None)
