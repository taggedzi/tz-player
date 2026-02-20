"""Audio beat/onset analysis helpers for lazy visualization beat data."""

from __future__ import annotations

import math
import shutil
import struct
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

_TARGET_SAMPLE_RATE = 11_025
_WAVE_SUFFIXES = {".wav", ".wave"}


@dataclass(frozen=True)
class BeatAnalysisResult:
    """Quantized onset/beat frames ready for persistent cache storage."""

    duration_ms: int
    bpm: float
    frames: list[tuple[int, int, bool]]


def analyze_track_beats(
    track_path: Path | str,
    *,
    hop_ms: int = 40,
    max_frames: int = 12_000,
) -> BeatAnalysisResult | None:
    """Decode track and compute onset-strength timeline with beat markers."""
    path = Path(track_path)
    if not path.exists() or not path.is_file():
        return None
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
    window_samples = max(hop_samples, hop_samples * 2)
    energies: list[float] = []
    for start in range(0, len(mono_samples), hop_samples):
        window = mono_samples[start : start + window_samples]
        if not window:
            continue
        energies.append(_rms_energy(window))
        if len(energies) >= max_frames:
            break
    if not energies:
        return None

    onsets = _onset_envelope(energies)
    max_onset = max(onsets) if onsets else 0.0
    if max_onset <= 0.0:
        strengths = [0.0 for _ in onsets]
    else:
        strengths = [min(1.0, value / max_onset) for value in onsets]

    fps = 1000.0 / hop_ms
    bpm, beat_lag = _estimate_bpm(onsets, fps=fps)
    beat_flags = _mark_beats(strengths, beat_lag)

    frames: list[tuple[int, int, bool]] = []
    for idx, strength in enumerate(strengths):
        position_ms = idx * hop_ms
        strength_u8 = int(max(0, min(255, round(strength * 255.0))))
        is_beat = beat_flags[idx] if idx < len(beat_flags) else False
        frames.append((position_ms, strength_u8, is_beat))

    duration_ms = int((len(mono_samples) * 1000) / sample_rate)
    if not frames:
        return None
    return BeatAnalysisResult(duration_ms=max(1, duration_ms), bpm=bpm, frames=frames)


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
                mono, frame_rate, _TARGET_SAMPLE_RATE
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
        str(_TARGET_SAMPLE_RATE),
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
        return _TARGET_SAMPLE_RATE, _pcm_to_mono(raw, channels=1, sample_width=2)
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
    return []


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


def _rms_energy(values: list[float]) -> float:
    if not values:
        return 0.0
    total = 0.0
    for value in values:
        total += value * value
    return math.sqrt(total / len(values))


def _onset_envelope(energies: list[float]) -> list[float]:
    if not energies:
        return []
    out = [0.0]
    for idx in range(1, len(energies)):
        diff = energies[idx] - energies[idx - 1]
        out.append(diff if diff > 0.0 else 0.0)
    return out


def _estimate_bpm(onsets: list[float], *, fps: float) -> tuple[float, int]:
    if len(onsets) < 8 or fps <= 0.0:
        return 0.0, 0
    min_bpm = 60.0
    max_bpm = 180.0
    lag_min = max(1, int(round((60.0 * fps) / max_bpm)))
    lag_max = max(lag_min + 1, int(round((60.0 * fps) / min_bpm)))
    lag_max = min(lag_max, len(onsets) - 1)
    if lag_max <= lag_min:
        return 0.0, 0

    best_lag = 0
    best_score = 0.0
    for lag in range(lag_min, lag_max + 1):
        score = 0.0
        for idx in range(lag, len(onsets)):
            score += onsets[idx] * onsets[idx - lag]
        if score > best_score:
            best_score = score
            best_lag = lag
    if best_lag <= 0 or best_score <= 0.0:
        return 0.0, 0
    bpm = (60.0 * fps) / best_lag
    return max(0.0, bpm), best_lag


def _mark_beats(strengths: list[float], lag: int) -> list[bool]:
    if not strengths or lag <= 0:
        return [False for _ in strengths]
    phase_scores = [0.0 for _ in range(lag)]
    for idx, strength in enumerate(strengths):
        phase_scores[idx % lag] += strength
    phase = max(range(lag), key=lambda value: phase_scores[value])
    mean_strength = sum(strengths) / len(strengths)
    threshold = max(0.12, mean_strength * 1.35)
    return [
        (idx % lag == phase) and (strength >= threshold)
        for idx, strength in enumerate(strengths)
    ]
