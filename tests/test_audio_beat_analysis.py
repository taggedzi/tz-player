"""Tests for audio beat analysis helpers."""

from __future__ import annotations

import math
import wave
from pathlib import Path

from tz_player.services.audio_beat_analysis import analyze_track_beats


def _write_wave(path: Path, *, frames: int = 2_205, sample_rate: int = 44_100) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        payload = bytearray()
        for idx in range(frames):
            value = int(20000 * math.sin((2.0 * math.pi * 440.0 * idx) / sample_rate))
            payload.extend(value.to_bytes(2, "little", signed=True))
        handle.writeframes(bytes(payload))


def test_analyze_track_beats_returns_frames_for_wave(tmp_path) -> None:
    track = tmp_path / "tone.wav"
    _write_wave(track, frames=44_100)

    result = analyze_track_beats(track, hop_ms=40)
    assert result is not None
    assert result.duration_ms > 0
    assert result.frames
    first = result.frames[0]
    assert len(first) == 3
    assert 0 <= first[1] <= 255
    assert isinstance(first[2], bool)
    assert result.bpm >= 0.0


def test_analyze_track_beats_returns_none_for_missing_file(tmp_path) -> None:
    missing = tmp_path / "missing.wav"
    assert analyze_track_beats(missing) is None
