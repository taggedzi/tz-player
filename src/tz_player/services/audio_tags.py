"""Audio metadata helpers using permissive libraries."""

from __future__ import annotations

import math
import re
import wave
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path


@dataclass(frozen=True)
class AudioTags:
    """Normalized metadata payload returned by tag-reading helpers."""

    title: str | None = None
    artist: str | None = None
    album: str | None = None
    year: int | None = None
    genre: str | None = None
    duration_ms: int | None = None
    bitrate_kbps: int | None = None
    error: str | None = None


def read_audio_tags(path: Path) -> AudioTags:
    """Read metadata for a track path using TinyTag with safe fallbacks."""
    tinytag_data = _read_with_tinytag(path)
    if tinytag_data is not None and tinytag_data.error is None:
        return tinytag_data
    wave_data = _read_wave_fallback(path)
    if wave_data is not None:
        return wave_data
    if tinytag_data is not None:
        return tinytag_data
    return AudioTags(error="Unsupported or unreadable file")


def _read_with_tinytag(path: Path) -> AudioTags | None:
    """Best-effort metadata read path via TinyTag dependency."""
    try:
        tinytag_module = import_module("tinytag")
        TinyTag = tinytag_module.TinyTag
    except Exception:
        return None
    try:
        tag = TinyTag.get(str(path))
    except Exception as exc:
        return AudioTags(error=str(exc))
    duration_ms = _safe_duration_ms(getattr(tag, "duration", None))
    bitrate_kbps = _safe_bitrate_kbps(getattr(tag, "bitrate", None))
    return AudioTags(
        title=_clean_text(tag.title),
        artist=_clean_text(tag.artist),
        album=_clean_text(tag.album),
        year=_parse_year(_clean_text(getattr(tag, "year", None))),
        genre=_clean_text(getattr(tag, "genre", None)),
        duration_ms=duration_ms,
        bitrate_kbps=bitrate_kbps,
    )


def _read_wave_fallback(path: Path) -> AudioTags | None:
    """Fallback duration/bitrate derivation for WAV files."""
    try:
        with wave.open(str(path), "rb") as handle:
            channels = int(handle.getnchannels())
            frame_rate = int(handle.getframerate())
            sample_width = int(handle.getsampwidth())
            frame_count = int(handle.getnframes())
    except Exception:
        return None
    if channels <= 0 or frame_rate <= 0 or sample_width <= 0:
        return None
    duration_ms = int((frame_count * 1000) / frame_rate)
    bitrate_kbps = int(round((frame_rate * sample_width * channels * 8) / 1000))
    return AudioTags(duration_ms=max(1, duration_ms), bitrate_kbps=bitrate_kbps)


def _clean_text(value: object) -> str | None:
    """Normalize textual metadata fields into trimmed optional strings."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_year(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"\b(\d{4})\b", value)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def _safe_duration_ms(value: object) -> int | None:
    if not isinstance(value, (int, float)):
        return None
    normalized = float(value)
    if not math.isfinite(normalized) or normalized <= 0:
        return None
    return int(normalized * 1000)


def _safe_bitrate_kbps(value: object) -> int | None:
    if not isinstance(value, (int, float)):
        return None
    normalized = float(value)
    if not math.isfinite(normalized) or normalized <= 0:
        return None
    return int(round(normalized))
