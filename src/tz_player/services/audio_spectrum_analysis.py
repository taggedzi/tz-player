"""Audio spectrum analysis helpers for lazy FFT-style visualization data."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from .audio_decode import DecodedAnalysisAudio, decode_track_for_analysis

_MIN_FREQ_HZ = 40.0
_MAX_FREQ_HZ = 5_000.0


@dataclass(frozen=True)
class SpectrumAnalysisResult:
    """Quantized spectrum frames ready for persistent cache storage."""

    duration_ms: int
    frames: list[tuple[int, bytes]]


def analyze_track_spectrum(
    track_path: Path | str,
    *,
    band_count: int = 48,
    hop_ms: int = 40,
    max_frames: int = 12_000,
) -> SpectrumAnalysisResult | None:
    """Decode track and compute quantized log-spaced spectrum frames."""
    path = Path(track_path)
    decoded = decode_track_for_analysis(path)
    if decoded is None:
        return None
    return analyze_spectrum_from_decoded(
        decoded,
        band_count=band_count,
        hop_ms=hop_ms,
        max_frames=max_frames,
    )


def analyze_spectrum_from_decoded(
    decoded: DecodedAnalysisAudio,
    *,
    band_count: int = 48,
    hop_ms: int = 40,
    max_frames: int = 12_000,
) -> SpectrumAnalysisResult | None:
    """Compute quantized log-spaced spectrum frames from decoded mono samples."""
    return analyze_spectrum_from_mono(
        decoded.mono_rate,
        decoded.mono_samples,
        band_count=band_count,
        hop_ms=hop_ms,
        max_frames=max_frames,
    )


def analyze_spectrum_from_mono(
    sample_rate: int,
    mono_samples: list[float],
    *,
    band_count: int = 48,
    hop_ms: int = 40,
    max_frames: int = 12_000,
) -> SpectrumAnalysisResult | None:
    """Compute quantized log-spaced spectrum frames from mono samples."""
    if sample_rate <= 0 or not mono_samples:
        return None
    band_count = max(8, int(band_count))
    hop_ms = max(10, int(hop_ms))

    hop_samples = max(1, int(sample_rate * (hop_ms / 1000.0)))
    window_size = _window_size(hop_samples)
    freqs = _log_frequencies(band_count, sample_rate)

    magnitudes: list[list[float]] = []
    frame_positions: list[int] = []
    for start in range(0, len(mono_samples), hop_samples):
        frame_positions.append(int((start * 1000) / sample_rate))
        window = mono_samples[start : start + window_size]
        if len(window) < window_size:
            window = [*window, *([0.0] * (window_size - len(window)))]
        windowed = _hann_window(window)
        magnitudes.append(_frame_magnitudes(windowed, sample_rate, freqs))

    if not magnitudes:
        return None

    max_mag = max(max(row) for row in magnitudes)
    if max_mag <= 0.0:
        max_mag = 1.0

    frames: list[tuple[int, bytes]] = []
    for idx, row in enumerate(magnitudes):
        if idx >= max_frames:
            break
        quantized = bytes(_quantize_level(value / max_mag) for value in row)
        frames.append((frame_positions[idx], quantized))

    duration_ms = int((len(mono_samples) * 1000) / sample_rate)
    if not frames:
        return None
    return SpectrumAnalysisResult(duration_ms=max(1, duration_ms), frames=frames)


def _window_size(hop_samples: int) -> int:
    target = max(256, hop_samples * 2)
    size = 1
    while size < target:
        size <<= 1
    return min(2048, size)


def _log_frequencies(band_count: int, sample_rate: int) -> list[float]:
    nyquist = max(100.0, (sample_rate / 2.0) - 1.0)
    min_freq = _MIN_FREQ_HZ
    max_freq = min(_MAX_FREQ_HZ, nyquist)
    if band_count <= 1:
        return [min_freq]
    ratio = (max_freq / min_freq) ** (1.0 / (band_count - 1))
    return [min_freq * (ratio**idx) for idx in range(band_count)]


def _hann_window(values: list[float]) -> list[float]:
    size = len(values)
    if size <= 1:
        return values
    return [
        values[idx] * (0.5 - (0.5 * math.cos((2.0 * math.pi * idx) / (size - 1))))
        for idx in range(size)
    ]


def _frame_magnitudes(
    window: list[float],
    sample_rate: int,
    freqs: list[float],
) -> list[float]:
    return [_goertzel_power(window, sample_rate, freq) for freq in freqs]


def _goertzel_power(samples: list[float], sample_rate: int, freq_hz: float) -> float:
    sample_count = len(samples)
    if sample_count <= 0 or sample_rate <= 0:
        return 0.0
    k = int(0.5 + ((sample_count * freq_hz) / sample_rate))
    omega = (2.0 * math.pi * k) / sample_count
    coeff = 2.0 * math.cos(omega)
    s_prev = 0.0
    s_prev2 = 0.0
    for sample in samples:
        s = sample + (coeff * s_prev) - s_prev2
        s_prev2 = s_prev
        s_prev = s
    power = (s_prev2 * s_prev2) + (s_prev * s_prev) - (coeff * s_prev * s_prev2)
    if power <= 0.0:
        return 0.0
    return math.log1p(power)


def _quantize_level(normalized: float) -> int:
    clamped = max(0.0, min(1.0, normalized))
    curved = math.sqrt(clamped)
    return int(round(curved * 255.0))
