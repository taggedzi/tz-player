"""Shared one-pass analysis pipeline for spectrum, beat, and waveform proxy."""

from __future__ import annotations

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

    decoded = decode_track_for_analysis(Path(track_path))
    if decoded is None:
        return None

    spectrum = (
        analyze_spectrum_from_decoded(
            decoded,
            band_count=spectrum_band_count,
            hop_ms=spectrum_hop_ms,
            max_frames=max_spectrum_frames,
        )
        if include_spectrum
        else None
    )
    beat = (
        analyze_beats_from_decoded(
            decoded,
            hop_ms=beat_hop_ms,
            max_frames=max_beat_frames,
        )
        if include_beat
        else None
    )
    waveform_proxy = (
        analyze_waveform_proxy_from_decoded(
            decoded,
            hop_ms=waveform_hop_ms,
            max_frames=max_waveform_frames,
        )
        if include_waveform_proxy
        else None
    )

    return AnalysisBundleResult(
        spectrum=spectrum,
        beat=beat,
        waveform_proxy=waveform_proxy,
    )
