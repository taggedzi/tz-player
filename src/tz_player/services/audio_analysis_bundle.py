"""Shared one-pass analysis pipeline for spectrum, beat, and waveform proxy."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from .audio_beat_analysis import BeatAnalysisResult, analyze_beats_from_decoded
from .audio_decode import decode_track_for_analysis
from .audio_spectrum_analysis import (
    SpectrumAnalysisResult,
    analyze_spectrum_from_decoded,
)
from .audio_waveform_proxy_analysis import (
    WaveformProxyAnalysisResult,
    analyze_waveform_proxy_from_decoded,
)


@dataclass(frozen=True)
class AnalysisBundleResult:
    """Combined lazy-analysis payload computed from a single decode pass."""

    spectrum: SpectrumAnalysisResult | None
    beat: BeatAnalysisResult | None
    waveform_proxy: WaveformProxyAnalysisResult | None
    timings: AnalysisBundleTimings | None = None


@dataclass(frozen=True)
class AnalysisBundleTimings:
    """Best-effort internal timing breakdown for one bundle analysis pass."""

    decode_ms: float
    spectrum_ms: float
    beat_ms: float
    waveform_proxy_ms: float
    total_ms: float


def analyze_track_analysis_bundle(
    track_path: Path | str,
    *,
    spectrum_band_count: int,
    spectrum_hop_ms: int,
    beat_hop_ms: int,
    waveform_hop_ms: int,
    max_spectrum_frames: int = 12_000,
    max_beat_frames: int = 12_000,
    max_waveform_frames: int = 30_000,
    include_spectrum: bool = True,
    include_beat: bool = True,
    include_waveform_proxy: bool = True,
) -> AnalysisBundleResult | None:
    """Compute requested analysis outputs from one decoded track pass."""
    if not include_spectrum and not include_beat and not include_waveform_proxy:
        return None

    bundle_start = time.perf_counter()
    decode_start = bundle_start
    decoded = decode_track_for_analysis(Path(track_path))
    decode_ms = (time.perf_counter() - decode_start) * 1000.0
    if decoded is None:
        return None

    spectrum_ms = 0.0
    beat_ms = 0.0
    waveform_ms = 0.0
    spectrum: SpectrumAnalysisResult | None = None
    if include_spectrum:
        spectrum, spectrum_ms = _timed_spectrum(
            decoded,
            band_count=spectrum_band_count,
            hop_ms=spectrum_hop_ms,
            max_frames=max_spectrum_frames,
        )
    beat: BeatAnalysisResult | None = None
    if include_beat:
        beat, beat_ms = _timed_beat(
            decoded,
            hop_ms=beat_hop_ms,
            max_frames=max_beat_frames,
        )
    waveform_proxy: WaveformProxyAnalysisResult | None = None
    if include_waveform_proxy:
        waveform_proxy, waveform_ms = _timed_waveform_proxy(
            decoded,
            hop_ms=waveform_hop_ms,
            max_frames=max_waveform_frames,
        )
    total_ms = (time.perf_counter() - bundle_start) * 1000.0

    return AnalysisBundleResult(
        spectrum=spectrum,
        beat=beat,
        waveform_proxy=waveform_proxy,
        timings=AnalysisBundleTimings(
            decode_ms=decode_ms,
            spectrum_ms=spectrum_ms,
            beat_ms=beat_ms,
            waveform_proxy_ms=waveform_ms,
            total_ms=total_ms,
        ),
    )


def _timed_spectrum(
    decoded,
    *,
    band_count: int,
    hop_ms: int,
    max_frames: int,
) -> tuple[SpectrumAnalysisResult | None, float]:
    start = time.perf_counter()
    result = analyze_spectrum_from_decoded(
        decoded,
        band_count=band_count,
        hop_ms=hop_ms,
        max_frames=max_frames,
    )
    return result, (time.perf_counter() - start) * 1000.0


def _timed_beat(
    decoded,
    *,
    hop_ms: int,
    max_frames: int,
) -> tuple[BeatAnalysisResult | None, float]:
    start = time.perf_counter()
    result = analyze_beats_from_decoded(
        decoded,
        hop_ms=hop_ms,
        max_frames=max_frames,
    )
    return result, (time.perf_counter() - start) * 1000.0


def _timed_waveform_proxy(
    decoded,
    *,
    hop_ms: int,
    max_frames: int,
) -> tuple[WaveformProxyAnalysisResult | None, float]:
    start = time.perf_counter()
    result = analyze_waveform_proxy_from_decoded(
        decoded,
        hop_ms=hop_ms,
        max_frames=max_frames,
    )
    return result, (time.perf_counter() - start) * 1000.0
