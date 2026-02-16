"""Shared media format helpers."""

from __future__ import annotations

from pathlib import Path

VLC_AUDIO_EXTENSIONS = frozenset(
    {
        ".aac",
        ".ac3",
        ".aiff",
        ".alac",
        ".ape",
        ".dsf",
        ".dff",
        ".flac",
        ".m4a",
        ".mka",
        ".mp2",
        ".mp3",
        ".ogg",
        ".opus",
        ".wav",
        ".wma",
    }
)


def is_supported_audio_file(path: Path) -> bool:
    """Return whether path suffix is in the app's supported audio set."""
    return path.suffix.lower() in VLC_AUDIO_EXTENSIONS
