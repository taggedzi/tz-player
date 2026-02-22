"""Waveform-proxy analysis helpers for lightweight PCM-like visualizer data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .audio_decode import DecodedAnalysisAudio, decode_track_for_analysis


@dataclass(frozen=True)
class WaveformProxyAnalysisResult:
    """Quantized waveform-proxy frames ready for persistent cache storage."""

    duration_ms: int
    frames: list[tuple[int, int, int, int, int]]


def analyze_track_waveform_proxy(
    track_path: Path | str,
    *,
    hop_ms: int = 20,
    max_frames: int = 30_000,
) -> WaveformProxyAnalysisResult | None:
    """Decode and derive signed min/max proxy levels for short time windows."""
    path = Path(track_path)
    decoded = decode_track_for_analysis(path)
    if decoded is None:
        return None
    return analyze_waveform_proxy_from_decoded(
        decoded,
        hop_ms=hop_ms,
        max_frames=max_frames,
    )


def analyze_waveform_proxy_from_decoded(
    decoded: DecodedAnalysisAudio,
    *,
    hop_ms: int = 20,
    max_frames: int = 30_000,
) -> WaveformProxyAnalysisResult | None:
    """Compute waveform proxy frames from decoded stereo samples."""
    return analyze_waveform_proxy_from_stereo(
        decoded.stereo_rate,
        decoded.left_samples,
        decoded.right_samples,
        hop_ms=hop_ms,
        max_frames=max_frames,
    )


def analyze_waveform_proxy_from_stereo(
    sample_rate: int,
    left_samples: list[float],
    right_samples: list[float],
    *,
    hop_ms: int = 20,
    max_frames: int = 30_000,
) -> WaveformProxyAnalysisResult | None:
    """Compute waveform proxy frames from stereo sample vectors."""
    if (
        sample_rate <= 0
        or not left_samples
        or len(left_samples) != len(right_samples)
        or max_frames <= 0
    ):
        return None
    hop_ms = max(10, int(hop_ms))
    hop_frames = max(1, int(sample_rate * (hop_ms / 1000.0)))

    frames: list[tuple[int, int, int, int, int]] = []
    total = len(left_samples)
    start = 0
    while start < total and len(frames) < max_frames:
        end = min(total, start + hop_frames)
        left_bucket = left_samples[start:end]
        right_bucket = right_samples[start:end]
        if not left_bucket or not right_bucket:
            break
        frames.append(
            (
                int((start * 1000) / sample_rate),
                _to_i8(min(left_bucket)),
                _to_i8(max(left_bucket)),
                _to_i8(min(right_bucket)),
                _to_i8(max(right_bucket)),
            )
        )
        start = end

    duration_ms = int((total * 1000) / sample_rate)
    if not frames:
        return None
    return WaveformProxyAnalysisResult(duration_ms=max(1, duration_ms), frames=frames)


def _clamp_sample(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))


def _to_i8(value: float) -> int:
    return max(-127, min(127, int(round(_clamp_sample(value) * 127.0))))
