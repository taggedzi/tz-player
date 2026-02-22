"""Shared audio decode helpers for offline analysis pipelines."""

from __future__ import annotations

import shutil
import struct
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

_MONO_TARGET_RATE = 11_025
_STEREO_TARGET_RATE = 44_100
_WAVE_SUFFIXES = {".wav", ".wave"}


@dataclass(frozen=True)
class DecodedAnalysisAudio:
    """Decoded PCM suitable for spectrum/beat/waveform analysis."""

    duration_ms: int
    mono_rate: int
    mono_samples: list[float]
    stereo_rate: int
    left_samples: list[float]
    right_samples: list[float]


def decode_track_for_analysis(track_path: Path | str) -> DecodedAnalysisAudio | None:
    """Decode media into mono (11.025k) and stereo (44.1k-ish) analysis streams."""
    path = Path(track_path)
    if not path.exists() or not path.is_file():
        return None

    decoded = _decode_wave(path)
    if decoded is None:
        if path.suffix.lower() in _WAVE_SUFFIXES:
            return None
        decoded = _decode_ffmpeg(path)
    if decoded is None:
        return None

    source_rate, left, right = decoded
    if source_rate <= 0 or not left or len(left) != len(right):
        return None

    stereo_rate, stereo_left, stereo_right = _resample_stereo(
        left,
        right,
        source_rate,
        _STEREO_TARGET_RATE,
    )
    mono_source = [
        (left_value + right_value) / 2.0
        for left_value, right_value in zip(stereo_left, stereo_right)
    ]
    mono_rate, mono_samples = _resample_mono(
        mono_source,
        stereo_rate,
        _MONO_TARGET_RATE,
    )

    if mono_rate <= 0 or not mono_samples or not stereo_left:
        return None

    duration_ms = int((len(mono_samples) * 1000) / mono_rate)
    return DecodedAnalysisAudio(
        duration_ms=max(1, duration_ms),
        mono_rate=mono_rate,
        mono_samples=mono_samples,
        stereo_rate=stereo_rate,
        left_samples=stereo_left,
        right_samples=stereo_right,
    )


def _decode_wave(path: Path) -> tuple[int, list[float], list[float]] | None:
    try:
        with wave.open(str(path), "rb") as handle:
            channels = int(handle.getnchannels())
            frame_rate = int(handle.getframerate())
            sample_width = int(handle.getsampwidth())
            if channels <= 0 or frame_rate <= 0 or sample_width <= 0:
                return None
            raw = handle.readframes(handle.getnframes())
            left, right = _pcm_to_stereo(
                raw,
                channels=channels,
                sample_width=sample_width,
            )
            if not left:
                return None
            return frame_rate, left, right
    except (wave.Error, EOFError, OSError, ValueError):
        return None


def _decode_ffmpeg(path: Path) -> tuple[int, list[float], list[float]] | None:
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
        "2",
        "-ar",
        str(_STEREO_TARGET_RATE),
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
        left: list[float] = []
        right: list[float] = []
        for left_raw, right_raw in struct.iter_unpack("<hh", raw):
            left.append(_clamp_sample(left_raw / 32768.0))
            right.append(_clamp_sample(right_raw / 32768.0))
        if not left:
            return None
        return _STEREO_TARGET_RATE, left, right
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()


def _pcm_to_stereo(
    raw: bytes,
    *,
    channels: int,
    sample_width: int,
) -> tuple[list[float], list[float]]:
    bytes_per_frame = channels * sample_width
    frame_count = len(raw) // bytes_per_frame
    if frame_count <= 0:
        return [], []

    left: list[float] = []
    right: list[float] = []
    max_value = _sample_max(sample_width)
    for frame_idx in range(frame_count):
        offset = frame_idx * bytes_per_frame
        left_sample = _read_sample(raw, offset, sample_width)
        right_sample = (
            _read_sample(raw, offset + sample_width, sample_width)
            if channels > 1
            else left_sample
        )
        left.append(_clamp_sample(left_sample / max_value))
        right.append(_clamp_sample(right_sample / max_value))
    return left, right


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


def _resample_stereo(
    left: list[float],
    right: list[float],
    source_rate: int,
    target_rate: int,
) -> tuple[int, list[float], list[float]]:
    if source_rate <= 0 or target_rate <= 0 or source_rate == target_rate:
        return source_rate, left, right
    step = source_rate / target_rate
    if step <= 1.0:
        return source_rate, left, right
    out_left: list[float] = []
    out_right: list[float] = []
    idx = 0.0
    size = min(len(left), len(right))
    while int(idx) < size:
        sample_idx = int(idx)
        out_left.append(left[sample_idx])
        out_right.append(right[sample_idx])
        idx += step
    return target_rate, out_left, out_right


def _clamp_sample(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))
