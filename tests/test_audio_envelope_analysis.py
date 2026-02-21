"""Tests for audio envelope analysis helpers."""

from __future__ import annotations

import math
import wave
from pathlib import Path

import tz_player.services.audio_envelope_analysis as envelope_module
from tz_player.services.audio_envelope_analysis import (
    analyze_track_envelope,
    clear_ffmpeg_probe_cache,
    ffmpeg_available,
    requires_ffmpeg_for_envelope,
)


def _write_wave(path: Path, *, seconds: float = 0.5, sample_rate: int = 8000) -> None:
    """Write stereo sine-wave fixture used by envelope analysis tests."""
    frame_count = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        for i in range(frame_count):
            value = int(12000 * math.sin(2.0 * math.pi * 220.0 * (i / sample_rate)))
            sample = value.to_bytes(2, "little", signed=True)
            handle.writeframesraw(sample + sample)


def test_analyze_track_envelope_reads_wave_points(tmp_path) -> None:
    track = tmp_path / "tone.wav"
    _write_wave(track, seconds=0.6)

    result = analyze_track_envelope(track, bucket_ms=50)
    assert result is not None
    assert result.duration_ms >= 590
    assert len(result.points) >= 8
    first = result.points[0]
    assert first[0] == 0
    assert 0.0 <= first[1] <= 1.0
    assert 0.0 <= first[2] <= 1.0


def test_analyze_track_envelope_limits_points(tmp_path) -> None:
    track = tmp_path / "tone.wav"
    _write_wave(track, seconds=1.0)

    result = analyze_track_envelope(track, bucket_ms=10, max_points=5)
    assert result is not None
    assert len(result.points) == 5


def test_analyze_track_envelope_limits_points_keeps_final_timestamp(tmp_path) -> None:
    track = tmp_path / "tone.wav"
    _write_wave(track, seconds=1.0)

    full = analyze_track_envelope(track, bucket_ms=10, max_points=10_000)
    limited = analyze_track_envelope(track, bucket_ms=10, max_points=5)

    assert full is not None
    assert limited is not None
    assert limited.points[-1][0] == full.points[-1][0]


def test_analyze_track_envelope_returns_none_for_missing_file(tmp_path) -> None:
    missing = tmp_path / "missing.wav"
    assert analyze_track_envelope(missing) is None


def test_analyze_track_envelope_returns_none_on_wave_decode_value_error(
    tmp_path, monkeypatch
) -> None:
    track = tmp_path / "tone.wav"
    _write_wave(track, seconds=0.2)

    def _raise(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise ValueError("unsupported sample shape")

    monkeypatch.setattr(envelope_module, "_levels_from_pcm", _raise)
    assert analyze_track_envelope(track) is None


def test_requires_ffmpeg_for_envelope_by_extension() -> None:
    assert requires_ffmpeg_for_envelope("/tmp/song.mp3") is True
    assert requires_ffmpeg_for_envelope("/tmp/song.flac") is True
    assert requires_ffmpeg_for_envelope("/tmp/song.wav") is False


def test_ffmpeg_available_uses_cached_probe(monkeypatch) -> None:
    clear_ffmpeg_probe_cache()
    calls = {"count": 0}

    def fake_which(binary: str) -> str | None:
        calls["count"] += 1
        assert binary == "ffmpeg"
        return "/usr/bin/ffmpeg"

    monkeypatch.setattr(envelope_module.shutil, "which", fake_which)

    assert ffmpeg_available() is True
    assert ffmpeg_available() is True
    assert calls["count"] == 1


def test_ffmpeg_available_refresh_reprobes(monkeypatch) -> None:
    clear_ffmpeg_probe_cache()
    calls = {"count": 0}

    def fake_which(_binary: str) -> str | None:
        calls["count"] += 1
        if calls["count"] == 1:
            return None
        return "/usr/bin/ffmpeg"

    monkeypatch.setattr(envelope_module.shutil, "which", fake_which)

    assert ffmpeg_available() is False
    assert ffmpeg_available(refresh=True) is True
    assert calls["count"] == 2
