"""Tests for audio waveform-proxy analysis helpers."""

from __future__ import annotations

import math
import wave
from pathlib import Path

from tz_player.services.audio_waveform_proxy_analysis import (
    analyze_track_waveform_proxy,
)


def _write_wave(path: Path, *, frames: int = 4_410, sample_rate: int = 44_100) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        payload = bytearray()
        for idx in range(frames):
            left = int(20000 * math.sin((2.0 * math.pi * 220.0 * idx) / sample_rate))
            right = int(12000 * math.sin((2.0 * math.pi * 440.0 * idx) / sample_rate))
            payload.extend(left.to_bytes(2, "little", signed=True))
            payload.extend(right.to_bytes(2, "little", signed=True))
        handle.writeframes(bytes(payload))


def test_analyze_track_waveform_proxy_returns_quantized_frames_for_wave(
    tmp_path,
) -> None:
    track = tmp_path / "tone.wav"
    _write_wave(track)

    result = analyze_track_waveform_proxy(track, hop_ms=20)
    assert result is not None
    assert result.duration_ms > 0
    assert result.frames
    first = result.frames[0]
    assert len(first) == 5
    assert all(-127 <= value <= 127 for value in first[1:])


def test_analyze_track_waveform_proxy_returns_none_for_missing_file(tmp_path) -> None:
    missing = tmp_path / "missing.wav"
    assert analyze_track_waveform_proxy(missing) is None
