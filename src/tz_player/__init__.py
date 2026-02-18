"""Top-level package for tz-player.

The package surface intentionally exports only `__version__`; runtime entrypoints
live in `app.py`, `gui.py`, and `cli.py`.
"""

from __future__ import annotations

from .version import __version__

__all__ = ["__version__"]
