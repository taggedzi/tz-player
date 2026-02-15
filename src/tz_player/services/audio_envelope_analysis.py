"""Audio envelope analysis helpers for precomputed visualization levels."""

from __future__ import annotations

import logging
import shutil
import struct
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_FFMPEG_SAMPLE_RATE = 44_100
_FFMPEG_CHANNELS = 2
_FFMPEG_BYTES_PER_SAMPLE = 2
_WAVE_SUFFIXES = {".wav", ".wave"}


@dataclass(frozen=True)
class EnvelopeAnalysisResult:
    duration_ms: int
    points: list[tuple[int, float, float]]


def analyze_track_envelope(
    track_path: Path | str,
    *,
    bucket_ms: int = 50,
    max_points: int = 12_000,
) -> EnvelopeAnalysisResult | None:
    """Decode and bucket a track into normalized timestamped level points."""
    path = Path(track_path)
    if not path.exists() or not path.is_file():
        return None
    bucket_ms = max(10, int(bucket_ms))

    wave_result = _analyze_wave(path, bucket_ms=bucket_ms)
    if wave_result is not None:
        return _limit_points(wave_result, max_points=max_points)
    # Wave files are decoded via Python's wave module only; if decode fails,
    # fail closed rather than falling back to ffmpeg with different behavior.
    if path.suffix.lower() in _WAVE_SUFFIXES:
        return None

    ffmpeg_result = _analyze_ffmpeg(path, bucket_ms=bucket_ms)
    if ffmpeg_result is None:
        return None
    return _limit_points(ffmpeg_result, max_points=max_points)


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def requires_ffmpeg_for_envelope(path: Path | str) -> bool:
    return Path(path).suffix.lower() not in _WAVE_SUFFIXES


def _analyze_wave(path: Path, *, bucket_ms: int) -> EnvelopeAnalysisResult | None:
    try:
        with wave.open(str(path), "rb") as handle:
            channels = int(handle.getnchannels())
            frame_rate = int(handle.getframerate())
            sample_width = int(handle.getsampwidth())
            frame_count = int(handle.getnframes())
            if channels <= 0 or frame_rate <= 0 or sample_width <= 0:
                return None
            bucket_frames = max(1, int(frame_rate * (bucket_ms / 1000.0)))
            points: list[tuple[int, float, float]] = []
            processed_frames = 0
            while processed_frames < frame_count:
                chunk_frames = min(bucket_frames, frame_count - processed_frames)
                raw = handle.readframes(chunk_frames)
                if not raw:
                    break
                levels, consumed_frames = _levels_from_pcm(
                    raw, channels=channels, sample_width=sample_width
                )
                if consumed_frames <= 0:
                    break
                position_ms = int((processed_frames * 1000) / frame_rate)
                points.append((position_ms, levels[0], levels[1]))
                processed_frames += consumed_frames
            duration_ms = int((frame_count * 1000) / frame_rate)
            if not points:
                return None
            return EnvelopeAnalysisResult(
                duration_ms=max(1, duration_ms), points=points
            )
    except (wave.Error, EOFError, OSError, ValueError):
        return None


def _analyze_ffmpeg(path: Path, *, bucket_ms: int) -> EnvelopeAnalysisResult | None:
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
        str(_FFMPEG_CHANNELS),
        "-ar",
        str(_FFMPEG_SAMPLE_RATE),
        "pipe:1",
    ]
    frame_bytes = _FFMPEG_CHANNELS * _FFMPEG_BYTES_PER_SAMPLE
    bucket_frames = max(1, int(_FFMPEG_SAMPLE_RATE * (bucket_ms / 1000.0)))
    proc: subprocess.Popen[bytes] | None = None
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if proc.stdout is None:
            return None
        points: list[tuple[int, float, float]] = []
        buffer = bytearray()
        left_sum = 0.0
        right_sum = 0.0
        bucket_count = 0
        bucket_start = 0
        total_frames = 0
        while True:
            chunk = proc.stdout.read(32_768)
            if not chunk:
                break
            buffer.extend(chunk)
            aligned_bytes = (len(buffer) // frame_bytes) * frame_bytes
            if aligned_bytes <= 0:
                continue
            frame_chunk = bytes(buffer[:aligned_bytes])
            del buffer[:aligned_bytes]
            for left_raw, right_raw in struct.iter_unpack("<hh", frame_chunk):
                left_sum += abs(left_raw) / 32768.0
                right_sum += abs(right_raw) / 32768.0
                bucket_count += 1
                total_frames += 1
                if bucket_count >= bucket_frames:
                    points.append(
                        (
                            int((bucket_start * 1000) / _FFMPEG_SAMPLE_RATE),
                            _clamp(left_sum / bucket_count),
                            _clamp(right_sum / bucket_count),
                        )
                    )
                    bucket_start += bucket_count
                    left_sum = 0.0
                    right_sum = 0.0
                    bucket_count = 0
        if bucket_count > 0:
            points.append(
                (
                    int((bucket_start * 1000) / _FFMPEG_SAMPLE_RATE),
                    _clamp(left_sum / bucket_count),
                    _clamp(right_sum / bucket_count),
                )
            )
        return_code = proc.wait(timeout=2.0)
        if return_code != 0 or not points:
            return None
        duration_ms = int((total_frames * 1000) / _FFMPEG_SAMPLE_RATE)
        return EnvelopeAnalysisResult(duration_ms=max(1, duration_ms), points=points)
    except (OSError, subprocess.SubprocessError):
        logger.debug("ffmpeg envelope analysis failed for %s", path)
        return None
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()


def _levels_from_pcm(
    raw: bytes, *, channels: int, sample_width: int
) -> tuple[tuple[float, float], int]:
    bytes_per_frame = channels * sample_width
    frames = len(raw) // bytes_per_frame
    if frames <= 0:
        return (0.0, 0.0), 0
    left_sum = 0.0
    right_sum = 0.0
    max_value = _sample_max(sample_width)
    for frame_idx in range(frames):
        offset = frame_idx * bytes_per_frame
        left_sample = _read_sample(raw, offset, sample_width)
        right_sample = (
            _read_sample(raw, offset + sample_width, sample_width)
            if channels > 1
            else left_sample
        )
        left_sum += abs(left_sample) / max_value
        right_sum += abs(right_sample) / max_value
    return (_clamp(left_sum / frames), _clamp(right_sum / frames)), frames


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


def _limit_points(
    result: EnvelopeAnalysisResult, *, max_points: int
) -> EnvelopeAnalysisResult:
    if max_points <= 0 or len(result.points) <= max_points:
        return result
    stride = max(1, len(result.points) // max_points)
    points = list(result.points[::stride])
    last = result.points[-1]
    if points[-1][0] != last[0]:
        points.append(last)
    if len(points) > max_points:
        if max_points == 1:
            points = [last]
        else:
            trimmed = points[: max_points - 1]
            if trimmed and trimmed[-1][0] == last[0]:
                points = trimmed
            else:
                points = [*trimmed, last]
    return EnvelopeAnalysisResult(duration_ms=result.duration_ms, points=points)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
