"""Simple VLC backend smoke test runner."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tz_player.services.vlc_backend import VLCPlaybackBackend


async def _run(path: Path) -> None:
    backend = VLCPlaybackBackend()

    async def _handler(event) -> None:
        print(event)

    backend.set_event_handler(_handler)
    await backend.start()
    await backend.play(1, str(path), 0)
    await asyncio.sleep(5)
    await backend.stop()
    await backend.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description="VLC backend smoke test.")
    parser.add_argument("path", type=Path, help="Path to an audio file.")
    args = parser.parse_args()
    asyncio.run(_run(args.path))


if __name__ == "__main__":
    main()
