"""Runtime configuration helpers."""

from __future__ import annotations


def resolve_log_level(*, verbose: bool, quiet: bool) -> str:
    """Resolve effective log level from CLI flags.

    Precedence is deterministic: --quiet overrides --verbose.
    """
    if quiet:
        return "WARNING"
    if verbose:
        return "DEBUG"
    return "INFO"
