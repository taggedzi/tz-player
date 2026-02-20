"""Audio spectrum analysis helpers for lazy FFT-style visualization data."""

from __future__ import annotations

import math
import shutil
import struct
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

_FFMPEG_SAMPLE_RATE = 11_025
_WAVE_SUFFIXES = {".wav", ".wave"}
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
    if not path.exists() or not path.is_file():
        return None
    band_count = max(8, int(band_count))
    hop_ms = max(10, int(hop_ms))

    decoded = _decode_wave(path)
    if decoded is None:
        if path.suffix.lower() in _WAVE_SUFFIXES:
            return None
        decoded = _decode_ffmpeg(path)
    if decoded is None:
        return None
    sample_rate, mono_samples = decoded
    if sample_rate <= 0 or not mono_samples:
        return None

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


def _decode_wave(path: Path) -> tuple[int, list[float]] | None:
    try:
        with wave.open(str(path), "rb") as handle:
            channels = int(handle.getnchannels())
            frame_rate = int(handle.getframerate())
            sample_width = int(handle.getsampwidth())
            if channels <= 0 or frame_rate <= 0 or sample_width <= 0:
                return None
            raw = handle.readframes(handle.getnframes())
            mono = _pcm_to_mono(raw, channels=channels, sample_width=sample_width)
            if not mono:
                return None
            sample_rate, resampled = _resample_mono(
                mono, frame_rate, _FFMPEG_SAMPLE_RATE
            )
            return sample_rate, resampled
    except (wave.Error, EOFError, OSError, ValueError):
        return None


def _decode_ffmpeg(path: Path) -> tuple[int, list[float]] | None:
    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin is None:
        return None
    cmd = [
        ffmpeg_bin,
        "-v",
        "error",
        "-i",
        str(path),
        "-vn",
        "-sn",
        "-dn",
        "-f",
        "s16le",
        "-acodec",
        "pcm_s16le",
        "-ac",
        "1",
        "-ar",
        str(_FFMPEG_SAMPLE_RATE),
        "pipe:1",
    ]
    proc: subprocess.Popen[bytes] | None = None
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if proc.stdout is None:
            return None
        raw = proc.stdout.read()
        code = proc.wait(timeout=4.0)
        if code != 0 or not raw:
            return None
        return _FFMPEG_SAMPLE_RATE, _pcm_to_mono(raw, channels=1, sample_width=2)
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()


def _pcm_to_mono(raw: bytes, *, channels: int, sample_width: int) -> list[float]:
    bytes_per_frame = channels * sample_width
    frame_count = len(raw) // bytes_per_frame
    if frame_count <= 0:
        return []
    if sample_width == 2:
        if channels == 1:
            return [sample / 32768.0 for (sample,) in struct.iter_unpack("<h", raw)]
        mono: list[float] = []
        for frame in struct.iter_unpack("<" + ("h" * channels), raw):
            mono.append(sum(frame) / (channels * 32768.0))
        return mono

    mono = []
    for frame_idx in range(frame_count):
        offset = frame_idx * bytes_per_frame
        total = 0.0
        for channel in range(channels):
            total += _read_sample(raw, offset + (channel * sample_width), sample_width)
        max_value = _sample_max(sample_width)
        mono.append((total / channels) / max_value)
    return mono


def _read_sample(raw: bytes, offset: int, sample_width: int) -> int:
    if sample_width == 1:
        return raw[offset] - 128
    if sample_width == 2:
        return int.from_bytes(raw[offset : offset + 2], "little", signed=True)
    if sample_width == 3:
        value = int.from_bytes(raw[offset : offset + 3], "little", signed=False)
        if value & 0x800000:
            value -= 0x1000000
        return value
    if sample_width == 4:
        return int.from_bytes(raw[offset : offset + 4], "little", signed=True)
    raise ValueError("Unsupported sample width")


def _sample_max(sample_width: int) -> float:
    if sample_width == 1:
        return 128.0
    if sample_width == 2:
        return 32768.0
    if sample_width == 3:
        return 8_388_608.0
    if sample_width == 4:
        return 2_147_483_648.0
    return 32768.0


def _resample_mono(
    samples: list[float],
    source_rate: int,
    target_rate: int,
) -> tuple[int, list[float]]:
    if source_rate <= 0 or target_rate <= 0 or source_rate == target_rate:
        return source_rate, samples
    step = source_rate / target_rate
    if step <= 1.0:
        return source_rate, samples
    out: list[float] = []
    idx = 0.0
    size = len(samples)
    while int(idx) < size:
        out.append(samples[int(idx)])
        idx += step
    return target_rate, out


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
