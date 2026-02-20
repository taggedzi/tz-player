"""Tests for audio beat analysis helpers."""

from __future__ import annotations

import math
import wave
from pathlib import Path

from tz_player.services.audio_beat_analysis import (
    analyze_track_beats,
    analyze_track_beats_librosa,
    librosa_available,
)


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


def _write_pulse_wave(
    path: Path,
    *,
    duration_s: float = 8.0,
    bpm: float = 120.0,
    sample_rate: int = 44_100,
) -> None:
    frame_count = int(duration_s * sample_rate)
    pulse_every = max(1, int(round((60.0 / bpm) * sample_rate)))
    pulse_len = max(1, int(0.018 * sample_rate))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        payload = bytearray()
        for idx in range(frame_count):
            tone = int(8000 * math.sin((2.0 * math.pi * 220.0 * idx) / sample_rate))
            pulse_pos = idx % pulse_every
            pulse_amp = 0
            if pulse_pos < pulse_len:
                env = 1.0 - (pulse_pos / pulse_len)
                pulse_amp = int(22000 * env)
            value = max(-32768, min(32767, tone + pulse_amp))
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


def test_analyze_track_beats_detects_repeating_pulses(tmp_path) -> None:
    track = tmp_path / "pulse.wav"
    _write_pulse_wave(track, bpm=120.0, duration_s=8.0)

    result = analyze_track_beats(track, hop_ms=40)
    assert result is not None
    assert (54.0 <= result.bpm <= 66.0) or (108.0 <= result.bpm <= 132.0)
    beat_count = sum(1 for _, _, is_beat in result.frames if is_beat)
    assert beat_count >= 8
    max_strength = max(strength for _, strength, _ in result.frames)
    assert max_strength >= 160


def test_librosa_availability_probe_returns_bool() -> None:
    assert isinstance(librosa_available(), bool)


def test_analyze_track_beats_librosa_returns_none_for_missing_file(tmp_path) -> None:
    missing = tmp_path / "missing.wav"
    assert analyze_track_beats_librosa(missing) is None
