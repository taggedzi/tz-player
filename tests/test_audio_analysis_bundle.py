"""Tests for shared one-pass spectrum/beat/waveform analysis bundle."""

from __future__ import annotations

import math
import wave
from pathlib import Path

from tz_player.services.audio_analysis_bundle import analyze_track_analysis_bundle
from tz_player.services.audio_beat_analysis import BeatAnalysisResult
from tz_player.services.audio_spectrum_analysis import SpectrumAnalysisResult
from tz_player.services.audio_spectrum_native_cli import (
    NativeSpectrumHelperAttempt,
    NativeSpectrumHelperResult,
    NativeSpectrumHelperTimingBreakdown,
)
from tz_player.services.audio_waveform_proxy_analysis import WaveformProxyAnalysisResult


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
    assert result.backend_info is not None
    assert result.backend_info.analysis_backend == "python"
    assert result.backend_info.fallback_reason is None


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


def test_analyze_track_analysis_bundle_uses_native_cli_for_spectrum_only(
    tmp_path, monkeypatch
) -> None:
    track = tmp_path / "tone.wav"
    _write_wave(track)

    def fake_native_helper(*args, **kwargs):  # noqa: ANN002, ANN003
        return NativeSpectrumHelperResult(
            spectrum=SpectrumAnalysisResult(
                duration_ms=1000,
                frames=[(0, bytes([1, 2, 3, 4]))],
            ),
            timings=None,
            helper_version="dev",
        )

    def fail_decode(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("decode should not run for native spectrum-only path")

    monkeypatch.setenv("TZ_PLAYER_NATIVE_SPECTRUM_HELPER_CMD", "fake-helper")
    monkeypatch.setattr(
        "tz_player.services.audio_analysis_bundle.analyze_track_spectrum_via_native_cli_attempt",
        lambda *args, **kwargs: NativeSpectrumHelperAttempt(
            result=fake_native_helper(*args, **kwargs),
            failure_reason=None,
        ),
    )
    monkeypatch.setattr(
        "tz_player.services.audio_analysis_bundle.decode_track_for_analysis",
        fail_decode,
    )

    result = analyze_track_analysis_bundle(
        track,
        spectrum_band_count=4,
        spectrum_hop_ms=40,
        beat_hop_ms=40,
        waveform_hop_ms=20,
        include_beat=False,
        include_waveform_proxy=False,
    )

    assert result is not None
    assert result.spectrum is not None
    assert result.spectrum.frames == [(0, bytes([1, 2, 3, 4]))]
    assert result.beat is None
    assert result.waveform_proxy is None
    assert result.backend_info is not None
    assert result.backend_info.analysis_backend == "native_helper"
    assert result.backend_info.spectrum_backend == "native_helper"
    assert result.backend_info.fallback_reason is None


def test_analyze_track_analysis_bundle_uses_native_spectrum_for_mixed_bundle(
    tmp_path, monkeypatch
) -> None:
    track = tmp_path / "tone.wav"
    _write_wave(track)

    def fake_native_helper(*args, **kwargs):  # noqa: ANN002, ANN003
        return NativeSpectrumHelperResult(
            spectrum=SpectrumAnalysisResult(
                duration_ms=1000,
                frames=[(0, bytes([9, 8, 7, 6]))],
            ),
            timings=None,
            helper_version="dev",
        )

    def fail_python_spectrum(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError(
            "python spectrum path should be skipped when helper succeeds"
        )

    monkeypatch.setenv("TZ_PLAYER_NATIVE_SPECTRUM_HELPER_CMD", "fake-helper")
    monkeypatch.setattr(
        "tz_player.services.audio_analysis_bundle.analyze_track_spectrum_via_native_cli_attempt",
        lambda *args, **kwargs: NativeSpectrumHelperAttempt(
            result=fake_native_helper(*args, **kwargs),
            failure_reason=None,
        ),
    )
    monkeypatch.setattr(
        "tz_player.services.audio_analysis_bundle._timed_spectrum",
        fail_python_spectrum,
    )

    result = analyze_track_analysis_bundle(
        track,
        spectrum_band_count=4,
        spectrum_hop_ms=40,
        beat_hop_ms=40,
        waveform_hop_ms=20,
    )

    assert result is not None
    assert result.spectrum is not None
    assert result.spectrum.frames == [(0, bytes([9, 8, 7, 6]))]
    assert result.beat is not None
    assert result.waveform_proxy is not None
    assert result.backend_info is not None
    assert result.backend_info.analysis_backend == "hybrid_native_spectrum_python_rest"
    assert result.backend_info.spectrum_backend == "native_helper"
    assert result.backend_info.duplicate_decode_for_mixed_bundle is True


def test_analyze_track_analysis_bundle_skips_python_decode_when_helper_supplies_waveform(
    tmp_path, monkeypatch
) -> None:
    track = tmp_path / "tone.wav"
    _write_wave(track)

    helper_waveform = WaveformProxyAnalysisResult(
        duration_ms=1000,
        frames=[(0, -10, 10, -8, 8)],
    )

    monkeypatch.setenv("TZ_PLAYER_NATIVE_SPECTRUM_HELPER_CMD", "fake-helper")
    monkeypatch.setattr(
        "tz_player.services.audio_analysis_bundle.analyze_track_spectrum_via_native_cli_attempt",
        lambda *args, **kwargs: NativeSpectrumHelperAttempt(
            result=NativeSpectrumHelperResult(
                spectrum=SpectrumAnalysisResult(
                    duration_ms=1000,
                    frames=[(0, bytes([9, 8, 7, 6]))],
                ),
                timings=NativeSpectrumHelperTimingBreakdown(
                    decode_ms=2.0,
                    spectrum_ms=3.0,
                    beat_ms=None,
                    waveform_proxy_ms=4.0,
                    total_ms=10.0,
                ),
                waveform_proxy=helper_waveform,
                helper_version="dev",
            ),
            failure_reason=None,
        ),
    )
    monkeypatch.setattr(
        "tz_player.services.audio_analysis_bundle.decode_track_for_analysis",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError(
                "python decode should be skipped when helper supplies spectrum+waveform"
            )
        ),
    )

    result = analyze_track_analysis_bundle(
        track,
        spectrum_band_count=4,
        spectrum_hop_ms=40,
        beat_hop_ms=40,
        waveform_hop_ms=20,
        include_beat=False,
        include_waveform_proxy=True,
    )

    assert result is not None
    assert result.spectrum is not None
    assert result.waveform_proxy == helper_waveform
    assert result.beat is None
    assert result.timings is not None
    assert result.timings.python_decode_ms == 0.0
    assert result.timings.native_helper_decode_ms == 2.0
    assert result.timings.waveform_proxy_ms == 4.0
    assert result.backend_info is not None
    assert result.backend_info.analysis_backend == "native_helper"
    assert result.backend_info.spectrum_backend == "native_helper"
    assert result.backend_info.waveform_proxy_backend == "native_helper"
    assert result.backend_info.duplicate_decode_for_mixed_bundle is False


def test_analyze_track_analysis_bundle_skips_python_decode_when_helper_supplies_full_bundle(
    tmp_path, monkeypatch
) -> None:
    track = tmp_path / "tone.wav"
    _write_wave(track)

    helper_waveform = WaveformProxyAnalysisResult(
        duration_ms=1000,
        frames=[(0, -10, 10, -8, 8)],
    )
    helper_beat = BeatAnalysisResult(
        duration_ms=1000,
        bpm=120.0,
        frames=[(0, 0, False), (40, 128, True)],
    )

    monkeypatch.setenv("TZ_PLAYER_NATIVE_SPECTRUM_HELPER_CMD", "fake-helper")
    monkeypatch.setattr(
        "tz_player.services.audio_analysis_bundle.analyze_track_spectrum_via_native_cli_attempt",
        lambda *args, **kwargs: NativeSpectrumHelperAttempt(
            result=NativeSpectrumHelperResult(
                spectrum=SpectrumAnalysisResult(
                    duration_ms=1000,
                    frames=[(0, bytes([9, 8, 7, 6]))],
                ),
                timings=NativeSpectrumHelperTimingBreakdown(
                    decode_ms=2.0,
                    spectrum_ms=3.0,
                    beat_ms=1.5,
                    waveform_proxy_ms=4.0,
                    total_ms=12.0,
                ),
                beat=helper_beat,
                waveform_proxy=helper_waveform,
                helper_version="dev",
            ),
            failure_reason=None,
        ),
    )
    monkeypatch.setattr(
        "tz_player.services.audio_analysis_bundle.decode_track_for_analysis",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("python decode should be skipped for full helper bundle")
        ),
    )

    result = analyze_track_analysis_bundle(
        track,
        spectrum_band_count=4,
        spectrum_hop_ms=40,
        beat_hop_ms=40,
        waveform_hop_ms=20,
    )

    assert result is not None
    assert result.spectrum is not None
    assert result.beat == helper_beat
    assert result.waveform_proxy == helper_waveform
    assert result.timings is not None
    assert result.timings.python_decode_ms == 0.0
    assert result.timings.native_helper_decode_ms == 2.0
    assert result.timings.beat_ms == 1.5
    assert result.backend_info is not None
    assert result.backend_info.analysis_backend == "native_helper"
    assert result.backend_info.spectrum_backend == "native_helper"
    assert result.backend_info.beat_backend == "native_helper"
    assert result.backend_info.waveform_proxy_backend == "native_helper"
    assert result.backend_info.duplicate_decode_for_mixed_bundle is False


def test_analyze_track_analysis_bundle_records_native_fallback_reason(
    tmp_path, monkeypatch
) -> None:
    track = tmp_path / "tone.wav"
    _write_wave(track)

    monkeypatch.setenv("TZ_PLAYER_NATIVE_SPECTRUM_HELPER_CMD", "fake-helper")
    monkeypatch.setattr(
        "tz_player.services.audio_analysis_bundle.analyze_track_spectrum_via_native_cli_attempt",
        lambda *args, **kwargs: NativeSpectrumHelperAttempt(
            result=None,
            failure_reason="native_helper_timeout",
        ),
    )

    result = analyze_track_analysis_bundle(
        track,
        spectrum_band_count=8,
        spectrum_hop_ms=40,
        beat_hop_ms=40,
        waveform_hop_ms=20,
    )

    assert result is not None
    assert result.backend_info is not None
    assert result.backend_info.analysis_backend == "python"
    assert result.backend_info.spectrum_backend == "python"
    assert result.backend_info.fallback_reason == "native_helper_timeout"
