"""Runtime configuration normalization helpers.

These helpers keep CLI flag interpretation deterministic across entrypoints.
"""

from __future__ import annotations

VISUALIZER_RESPONSIVENESS_PROFILES = ("safe", "balanced", "aggressive")
_VISUALIZER_PROFILE_DEFAULT_FPS = {
    "safe": 10,
    "balanced": 16,
    "aggressive": 22,
}


def resolve_log_level(*, verbose: bool, quiet: bool) -> str:
    """Resolve effective log level from CLI flags.

    Precedence is deterministic: --quiet overrides --verbose.
    """
    if quiet:
        return "WARNING"
    if verbose:
        return "DEBUG"
    return "INFO"


def normalize_visualizer_responsiveness_profile(value: str) -> str:
    """Normalize persisted/CLI profile value to a supported profile name."""
    normalized = value.strip().lower()
    if normalized in VISUALIZER_RESPONSIVENESS_PROFILES:
        return normalized
    return "balanced"


def profile_default_visualizer_fps(profile: str) -> int:
    """Return default FPS for a responsiveness profile."""
    normalized = normalize_visualizer_responsiveness_profile(profile)
    return _VISUALIZER_PROFILE_DEFAULT_FPS[normalized]
