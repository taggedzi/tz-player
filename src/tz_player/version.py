"""Project version source of truth."""

from __future__ import annotations

import platform

__all__ = ["PROJECT_URL", "__version__", "build_help_epilog"]

# Manually updated for each release.
__version__ = "0.5.3"
PROJECT_URL = "https://github.com/taggedzi/tz-player"


def build_help_epilog() -> str:
    return (
        f"Project URL: {PROJECT_URL}\n"
        f"Platform: {platform.platform()}\n"
        f"Version: {__version__}"
    )
