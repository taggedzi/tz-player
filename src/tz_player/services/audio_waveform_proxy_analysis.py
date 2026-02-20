"""Waveform-proxy analysis helpers for lightweight PCM-like visualizer data."""

from __future__ import annotations

import shutil
import struct
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

_FFMPEG_SAMPLE_RATE = 44_100
_FFMPEG_CHANNELS = 2
_WAVE_SUFFIXES = {".wav", ".wave"}


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
    if not path.exists() or not path.is_file():
        return None
    hop_ms = max(10, int(hop_ms))

    wave_result = _analyze_wave(path, hop_ms=hop_ms, max_frames=max_frames)
    if wave_result is not None:
        return wave_result
    if path.suffix.lower() in _WAVE_SUFFIXES:
        return None
    return _analyze_ffmpeg(path, hop_ms=hop_ms, max_frames=max_frames)


def _analyze_wave(
    path: Path,
    *,
    hop_ms: int,
    max_frames: int,
) -> WaveformProxyAnalysisResult | None:
    try:
        with wave.open(str(path), "rb") as handle:
            channels = int(handle.getnchannels())
            frame_rate = int(handle.getframerate())
            sample_width = int(handle.getsampwidth())
            frame_count = int(handle.getnframes())
            if channels <= 0 or frame_rate <= 0 or sample_width <= 0:
                return None
            hop_frames = max(1, int(frame_rate * (hop_ms / 1000.0)))
            frames: list[tuple[int, int, int, int, int]] = []
            processed = 0
            while processed < frame_count and len(frames) < max_frames:
                chunk_frames = min(hop_frames, frame_count - processed)
                raw = handle.readframes(chunk_frames)
                if not raw:
                    break
                proxy, consumed = _proxy_from_pcm(
                    raw, channels=channels, sample_width=sample_width
                )
                if consumed <= 0:
                    break
                position_ms = int((processed * 1000) / frame_rate)
                frames.append(
                    (
                        position_ms,
                        proxy[0],
                        proxy[1],
                        proxy[2],
                        proxy[3],
                    )
                )
                processed += consumed
            duration_ms = int((frame_count * 1000) / frame_rate)
            if not frames:
                return None
            return WaveformProxyAnalysisResult(
                duration_ms=max(1, duration_ms), frames=frames
            )
    except (wave.Error, EOFError, OSError, ValueError):
        return None


def _analyze_ffmpeg(
    path: Path,
    *,
    hop_ms: int,
    max_frames: int,
) -> WaveformProxyAnalysisResult | None:
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
    proc: subprocess.Popen[bytes] | None = None
    hop_frames = max(1, int(_FFMPEG_SAMPLE_RATE * (hop_ms / 1000.0)))
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if proc.stdout is None:
            return None
        frames: list[tuple[int, int, int, int, int]] = []
        buffer = bytearray()
        total_frames = 0
        bucket_frames = 0
        bucket_start = 0
        min_left = 1.0
        max_left = -1.0
        min_right = 1.0
        max_right = -1.0
        while len(frames) < max_frames:
            chunk = proc.stdout.read(32_768)
            if not chunk:
                break
            buffer.extend(chunk)
            aligned_bytes = (len(buffer) // 4) * 4
            if aligned_bytes <= 0:
                continue
            frame_chunk = bytes(buffer[:aligned_bytes])
            del buffer[:aligned_bytes]
            for left_raw, right_raw in struct.iter_unpack("<hh", frame_chunk):
                left = _clamp_sample(left_raw / 32768.0)
                right = _clamp_sample(right_raw / 32768.0)
                min_left = min(min_left, left)
                max_left = max(max_left, left)
                min_right = min(min_right, right)
                max_right = max(max_right, right)
                bucket_frames += 1
                total_frames += 1
                if bucket_frames >= hop_frames:
                    frames.append(
                        (
                            int((bucket_start * 1000) / _FFMPEG_SAMPLE_RATE),
                            _to_i8(min_left),
                            _to_i8(max_left),
                            _to_i8(min_right),
                            _to_i8(max_right),
                        )
                    )
                    bucket_start += bucket_frames
                    bucket_frames = 0
                    min_left = 1.0
                    max_left = -1.0
                    min_right = 1.0
                    max_right = -1.0
                    if len(frames) >= max_frames:
                        break
        if bucket_frames > 0 and len(frames) < max_frames:
            frames.append(
                (
                    int((bucket_start * 1000) / _FFMPEG_SAMPLE_RATE),
                    _to_i8(min_left),
                    _to_i8(max_left),
                    _to_i8(min_right),
                    _to_i8(max_right),
                )
            )
        code = proc.wait(timeout=2.0)
        if code != 0 or not frames:
            return None
        duration_ms = int((total_frames * 1000) / _FFMPEG_SAMPLE_RATE)
        return WaveformProxyAnalysisResult(
            duration_ms=max(1, duration_ms), frames=frames
        )
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()


def _proxy_from_pcm(
    raw: bytes, *, channels: int, sample_width: int
) -> tuple[tuple[int, int, int, int], int]:
    bytes_per_frame = channels * sample_width
    frame_count = len(raw) // bytes_per_frame
    if frame_count <= 0:
        return (0, 0, 0, 0), 0

    min_left = 1.0
    max_left = -1.0
    min_right = 1.0
    max_right = -1.0
    max_value = _sample_max(sample_width)
    for frame_idx in range(frame_count):
        offset = frame_idx * bytes_per_frame
        left_sample = _read_sample(raw, offset, sample_width)
        right_sample = (
            _read_sample(raw, offset + sample_width, sample_width)
            if channels > 1
            else left_sample
        )
        left = _clamp_sample(left_sample / max_value)
        right = _clamp_sample(right_sample / max_value)
        min_left = min(min_left, left)
        max_left = max(max_left, left)
        min_right = min(min_right, right)
        max_right = max(max_right, right)
    return (
        _to_i8(min_left),
        _to_i8(max_left),
        _to_i8(min_right),
        _to_i8(max_right),
    ), frame_count


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


def _clamp_sample(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))


def _to_i8(value: float) -> int:
    return max(-127, min(127, int(round(_clamp_sample(value) * 127.0))))
