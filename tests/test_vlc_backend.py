"""Optional VLC backend smoke tests."""

from __future__ import annotations

import asyncio
import os

import pytest

try:
    import vlc  # noqa: F401
except (ImportError, OSError, FileNotFoundError) as exc:
    pytest.skip(f"python-vlc/libVLC unavailable: {exc}", allow_module_level=True)

from tz_player.services.vlc_backend import VLCPlaybackBackend


@pytest.mark.skipif(
    os.getenv("TZ_PLAYER_TEST_VLC") != "1",
    reason="Set TZ_PLAYER_TEST_VLC=1 to run VLC backend tests.",
)
def test_vlc_backend_start_stop() -> None:
    async def run() -> None:
        backend = VLCPlaybackBackend()

        async def _handler(_event) -> None:
            return None

        backend.set_event_handler(_handler)
        await backend.start()
        await backend.shutdown()

    asyncio.run(run())
