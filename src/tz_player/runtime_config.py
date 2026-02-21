"""Runtime configuration normalization helpers.

These helpers keep CLI flag interpretation deterministic across entrypoints.
"""

from __future__ import annotations

VISUALIZER_RESPONSIVENESS_PROFILES = ("safe", "balanced", "aggressive")
_VISUALIZER_PROFILE_DEFAULT_FPS = {
    "safe": 10,
    "balanced": 14,
    "aggressive": 22,
}
_VISUALIZER_PROFILE_SPECTRUM_HOP_MS = {
    "safe": 40,
    "balanced": 32,
    "aggressive": 24,
}
_VISUALIZER_PROFILE_BEAT_HOP_MS = {
    "safe": 40,
    "balanced": 32,
    "aggressive": 24,
}
_VISUALIZER_PROFILE_POLL_INTERVAL_S = {
    "safe": 0.25,
    "balanced": 0.18,
    "aggressive": 0.12,
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


def profile_default_spectrum_hop_ms(profile: str) -> int:
    """Return default spectrum hop interval for a responsiveness profile."""
    normalized = normalize_visualizer_responsiveness_profile(profile)
    return _VISUALIZER_PROFILE_SPECTRUM_HOP_MS[normalized]


def profile_default_beat_hop_ms(profile: str) -> int:
    """Return default beat hop interval for a responsiveness profile."""
    normalized = normalize_visualizer_responsiveness_profile(profile)
    return _VISUALIZER_PROFILE_BEAT_HOP_MS[normalized]


def profile_default_player_poll_interval_s(profile: str) -> float:
    """Return default player polling interval for a responsiveness profile."""
    normalized = normalize_visualizer_responsiveness_profile(profile)
    return _VISUALIZER_PROFILE_POLL_INTERVAL_S[normalized]
