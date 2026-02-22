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
from .audio_spectrum_native_cli import (
    analyze_track_spectrum_via_native_cli_attempt,
    get_native_spectrum_helper_config,
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
    backend_info: AnalysisBundleBackendInfo | None = None


@dataclass(frozen=True)
class AnalysisBundleTimings:
    """Best-effort internal timing breakdown for one bundle analysis pass."""

    decode_ms: float
    spectrum_ms: float
    beat_ms: float
    waveform_proxy_ms: float
    total_ms: float
    python_decode_ms: float = 0.0
    native_helper_decode_ms: float = 0.0
    native_helper_total_ms: float = 0.0


@dataclass(frozen=True)
class AnalysisBundleBackendInfo:
    """Structured observability fields describing analysis backend selection."""

    analysis_backend: str
    spectrum_backend: str | None
    beat_backend: str | None = None
    waveform_proxy_backend: str | None = None
    fallback_reason: str | None = None
    native_helper_version: str | None = None
    duplicate_decode_for_mixed_bundle: bool = False


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
    native_helper_requested = False
    native_fallback_reason: str | None = None
    helper_decode_ms = 0.0
    helper_spectrum_ms = 0.0
    helper_beat_ms = 0.0
    helper_waveform_ms = 0.0
    helper_version: str | None = None
    used_native_spectrum = False
    helper_attempt = None
    helper_beat: BeatAnalysisResult | None = None
    helper_waveform: WaveformProxyAnalysisResult | None = None

    spectrum: SpectrumAnalysisResult | None = None
    if include_spectrum:
        native_helper_requested = get_native_spectrum_helper_config() is not None
        helper_attempt = analyze_track_spectrum_via_native_cli_attempt(
            track_path,
            band_count=spectrum_band_count,
            hop_ms=spectrum_hop_ms,
            max_frames=max_spectrum_frames,
            waveform_hop_ms=waveform_hop_ms if include_waveform_proxy else None,
            max_waveform_frames=max_waveform_frames if include_waveform_proxy else None,
            beat_hop_ms=beat_hop_ms if include_beat else None,
            max_beat_frames=max_beat_frames if include_beat else None,
        )
        helper_result = helper_attempt.result
        if helper_result is not None:
            used_native_spectrum = True
            spectrum = helper_result.spectrum
            helper_version = helper_result.helper_version
            if helper_result.timings is not None:
                helper_decode_ms = max(0.0, helper_result.timings.decode_ms or 0.0)
                helper_spectrum_ms = max(0.0, helper_result.timings.spectrum_ms or 0.0)
                helper_beat_ms = max(0.0, helper_result.timings.beat_ms or 0.0)
                helper_waveform_ms = max(
                    0.0, helper_result.timings.waveform_proxy_ms or 0.0
                )
            helper_beat = helper_result.beat if include_beat else None
            helper_waveform = (
                helper_result.waveform_proxy if include_waveform_proxy else None
            )
            helper_satisfies_beat = (not include_beat) or (helper_beat is not None)
            helper_satisfies_waveform = (not include_waveform_proxy) or (
                helper_waveform is not None
            )
            if helper_satisfies_beat and helper_satisfies_waveform:
                total_ms = (time.perf_counter() - bundle_start) * 1000.0
                return AnalysisBundleResult(
                    spectrum=spectrum,
                    beat=helper_beat,
                    waveform_proxy=helper_waveform,
                    timings=AnalysisBundleTimings(
                        decode_ms=helper_decode_ms,
                        spectrum_ms=helper_spectrum_ms,
                        beat_ms=helper_beat_ms if helper_beat else 0.0,
                        waveform_proxy_ms=helper_waveform_ms
                        if helper_waveform
                        else 0.0,
                        total_ms=helper_result.timings.total_ms
                        if helper_result.timings is not None
                        and helper_result.timings.total_ms is not None
                        else total_ms,
                        python_decode_ms=0.0,
                        native_helper_decode_ms=helper_decode_ms,
                        native_helper_total_ms=helper_result.timings.total_ms
                        if helper_result.timings is not None
                        and helper_result.timings.total_ms is not None
                        else total_ms,
                    ),
                    backend_info=AnalysisBundleBackendInfo(
                        analysis_backend="native_helper",
                        spectrum_backend="native_helper",
                        beat_backend=(
                            "native_helper"
                            if include_beat and helper_beat is not None
                            else None
                        ),
                        waveform_proxy_backend=(
                            "native_helper"
                            if include_waveform_proxy and helper_waveform is not None
                            else None
                        ),
                        native_helper_version=helper_version,
                    ),
                )
        else:
            helper_beat = None
            helper_waveform = None
            if native_helper_requested:
                native_fallback_reason = (
                    helper_attempt.failure_reason
                    or "native_helper_unavailable_or_invalid_output"
                )
    else:
        helper_beat = None
        helper_waveform = None

    if (
        include_spectrum
        and not used_native_spectrum
        and native_helper_requested
        and helper_attempt is not None
        and helper_attempt.failure_reason
        and native_fallback_reason is None
    ):
        native_fallback_reason = (
            helper_attempt.failure_reason
            or "native_helper_unavailable_or_invalid_output"
        )

    decode_start = bundle_start
    decoded = decode_track_for_analysis(Path(track_path))
    python_decode_ms = (time.perf_counter() - decode_start) * 1000.0
    if decoded is None:
        return None

    spectrum_ms = helper_spectrum_ms
    beat_ms = 0.0
    waveform_ms = 0.0
    if include_spectrum and not used_native_spectrum:
        spectrum, spectrum_ms = _timed_spectrum(
            decoded,
            band_count=spectrum_band_count,
            hop_ms=spectrum_hop_ms,
            max_frames=max_spectrum_frames,
        )
    beat: BeatAnalysisResult | None = None
    if include_beat and helper_beat is not None:
        beat = helper_beat
        beat_ms = helper_beat_ms
    elif include_beat:
        beat, beat_ms = _timed_beat(
            decoded,
            hop_ms=beat_hop_ms,
            max_frames=max_beat_frames,
        )
    waveform_proxy: WaveformProxyAnalysisResult | None = None
    if include_waveform_proxy and helper_waveform is not None:
        waveform_proxy = helper_waveform
        waveform_ms = helper_waveform_ms
    elif include_waveform_proxy:
        waveform_proxy, waveform_ms = _timed_waveform_proxy(
            decoded,
            hop_ms=waveform_hop_ms,
            max_frames=max_waveform_frames,
        )
    total_ms = (time.perf_counter() - bundle_start) * 1000.0
    python_work_after_helper = (include_beat and helper_beat is None) or (
        include_waveform_proxy and helper_waveform is None
    )
    duplicate_decode_for_mixed_bundle = bool(
        used_native_spectrum and python_work_after_helper
    )
    decode_ms = python_decode_ms + (helper_decode_ms if used_native_spectrum else 0.0)
    if used_native_spectrum and python_work_after_helper:
        analysis_backend = "hybrid_native_spectrum_python_rest"
    elif used_native_spectrum:
        analysis_backend = "native_helper"
    else:
        analysis_backend = "python"
    spectrum_backend = (
        "native_helper"
        if used_native_spectrum
        else ("python" if include_spectrum else None)
    )
    beat_backend = (
        "native_helper"
        if include_beat and helper_beat is not None
        else ("python" if include_beat else None)
    )
    waveform_proxy_backend = (
        "native_helper"
        if include_waveform_proxy and helper_waveform is not None
        else ("python" if include_waveform_proxy else None)
    )

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
            python_decode_ms=python_decode_ms,
            native_helper_decode_ms=helper_decode_ms if used_native_spectrum else 0.0,
            native_helper_total_ms=(
                helper_decode_ms + helper_spectrum_ms + helper_waveform_ms
                if used_native_spectrum
                else 0.0
            ),
        ),
        backend_info=AnalysisBundleBackendInfo(
            analysis_backend=analysis_backend,
            spectrum_backend=spectrum_backend,
            beat_backend=beat_backend,
            waveform_proxy_backend=waveform_proxy_backend,
            fallback_reason=native_fallback_reason,
            native_helper_version=helper_version,
            duplicate_decode_for_mixed_bundle=duplicate_decode_for_mixed_bundle,
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
