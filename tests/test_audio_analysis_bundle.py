"""Tests for shared one-pass spectrum/beat/waveform analysis bundle."""

from __future__ import annotations

import math
import wave
from pathlib import Path

from tz_player.services.audio_analysis_bundle import analyze_track_analysis_bundle


def _write_wave(path: Path, *, frames: int = 44_100, sample_rate: int = 44_100) -> None:
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


def test_analyze_track_analysis_bundle_returns_all_outputs(tmp_path) -> None:
    track = tmp_path / "tone.wav"
    _write_wave(track)

    result = analyze_track_analysis_bundle(
        track,
        spectrum_band_count=8,
        spectrum_hop_ms=40,
        beat_hop_ms=40,
        waveform_hop_ms=20,
    )

    assert result is not None
    assert result.spectrum is not None
    assert result.beat is not None
    assert result.waveform_proxy is not None
    assert result.spectrum.frames
    assert result.beat.frames
    assert result.waveform_proxy.frames


def test_analyze_track_analysis_bundle_respects_include_flags(tmp_path) -> None:
    track = tmp_path / "tone.wav"
    _write_wave(track)

    result = analyze_track_analysis_bundle(
        track,
        spectrum_band_count=8,
        spectrum_hop_ms=40,
        beat_hop_ms=40,
        waveform_hop_ms=20,
        include_spectrum=False,
        include_waveform_proxy=False,
    )

    assert result is not None
    assert result.spectrum is None
    assert result.waveform_proxy is None
    assert result.beat is not None
