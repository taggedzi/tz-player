"""Tests for permissive audio metadata helpers."""

from __future__ import annotations

import wave
from pathlib import Path

from tz_player.services.audio_tags import read_audio_tags


def _write_wave(path: Path, duration_sec: float = 0.5, framerate: int = 44100) -> None:
    frames = int(duration_sec * framerate)
    with wave.open(str(path), "wb") as wave_file:
        wave_file.setnchannels(2)
        wave_file.setsampwidth(2)
        wave_file.setframerate(framerate)
        silence = (0).to_bytes(2, byteorder="little", signed=True)
        wave_file.writeframes(silence * frames * 2)


def test_read_audio_tags_wave_fallback_duration_and_bitrate(tmp_path) -> None:
    path = tmp_path / "tone.wav"
    _write_wave(path, duration_sec=0.5, framerate=44100)
    tags = read_audio_tags(path)
    assert tags.duration_ms is not None
    assert tags.duration_ms > 0
    assert tags.bitrate_kbps is not None
    assert tags.bitrate_kbps > 0


def test_read_audio_tags_missing_file_reports_error(tmp_path) -> None:
    path = tmp_path / "missing.mp3"
    tags = read_audio_tags(path)
    assert tags.error is not None
