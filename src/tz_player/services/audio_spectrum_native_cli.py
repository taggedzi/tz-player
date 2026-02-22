"""Optional native spectrum analysis helper integration via CLI subprocess."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .audio_beat_analysis import BeatAnalysisResult
from .audio_spectrum_analysis import SpectrumAnalysisResult
from .audio_waveform_proxy_analysis import WaveformProxyAnalysisResult

NATIVE_SPECTRUM_HELPER_CMD_ENV = "TZ_PLAYER_NATIVE_SPECTRUM_HELPER_CMD"
NATIVE_SPECTRUM_HELPER_TIMEOUT_ENV = "TZ_PLAYER_NATIVE_SPECTRUM_HELPER_TIMEOUT_S"
_DEFAULT_HELPER_TIMEOUT_S = 8.0
_MONO_TARGET_RATE_HZ = 11_025
_REQUEST_SCHEMA = "tz_player.native_spectrum_helper_request.v1"
_RESPONSE_SCHEMA = "tz_player.native_spectrum_helper_response.v1"


@dataclass(frozen=True)
class NativeSpectrumHelperConfig:
    """Resolved CLI helper settings for opt-in native spectrum analysis."""

    argv: tuple[str, ...]
    timeout_s: float


@dataclass(frozen=True)
class NativeSpectrumHelperTimingBreakdown:
    """Optional helper-reported timing breakdown in milliseconds."""

    decode_ms: float | None
    spectrum_ms: float | None
    beat_ms: float | None
    waveform_proxy_ms: float | None
    total_ms: float | None


@dataclass(frozen=True)
class NativeSpectrumHelperResult:
    """Parsed native-helper spectrum output and optional metadata."""

    spectrum: SpectrumAnalysisResult
    timings: NativeSpectrumHelperTimingBreakdown | None
    beat: BeatAnalysisResult | None = None
    waveform_proxy: WaveformProxyAnalysisResult | None = None
    helper_version: str | None = None


@dataclass(frozen=True)
class NativeSpectrumHelperAttempt:
    """Result of attempting native-helper analysis, including failure reason."""

    result: NativeSpectrumHelperResult | None
    failure_reason: str | None = None


def get_native_spectrum_helper_config(
    env: Mapping[str, str] | None = None,
) -> NativeSpectrumHelperConfig | None:
    """Return helper config when the CLI helper env var is enabled."""
    values = os.environ if env is None else env
    raw_cmd = values.get(NATIVE_SPECTRUM_HELPER_CMD_ENV, "").strip()
    if not raw_cmd:
        return None
    try:
        argv = tuple(shlex.split(raw_cmd, posix=(os.name != "nt")))
    except ValueError:
        return None
    if not argv:
        return None
    timeout_s = _parse_timeout_s(values.get(NATIVE_SPECTRUM_HELPER_TIMEOUT_ENV))
    return NativeSpectrumHelperConfig(argv=argv, timeout_s=timeout_s)


def analyze_track_spectrum_via_native_cli(
    track_path: Path | str,
    *,
    band_count: int,
    hop_ms: int,
    max_frames: int,
    waveform_hop_ms: int | None = None,
    max_waveform_frames: int | None = None,
    beat_hop_ms: int | None = None,
    max_beat_frames: int | None = None,
    env: Mapping[str, str] | None = None,
) -> NativeSpectrumHelperResult | None:
    """Invoke optional CLI helper and parse a spectrum payload if configured."""
    return analyze_track_spectrum_via_native_cli_attempt(
        track_path,
        band_count=band_count,
        hop_ms=hop_ms,
        max_frames=max_frames,
        waveform_hop_ms=waveform_hop_ms,
        max_waveform_frames=max_waveform_frames,
        beat_hop_ms=beat_hop_ms,
        max_beat_frames=max_beat_frames,
        env=env,
    ).result


def analyze_track_spectrum_via_native_cli_attempt(
    track_path: Path | str,
    *,
    band_count: int,
    hop_ms: int,
    max_frames: int,
    waveform_hop_ms: int | None = None,
    max_waveform_frames: int | None = None,
    beat_hop_ms: int | None = None,
    max_beat_frames: int | None = None,
    env: Mapping[str, str] | None = None,
) -> NativeSpectrumHelperAttempt:
    """Invoke optional CLI helper and return parsed output plus failure reason."""
    config = get_native_spectrum_helper_config(env)
    if config is None:
        return NativeSpectrumHelperAttempt(result=None, failure_reason=None)

    request_payload: dict[str, object] = {
        "schema": _REQUEST_SCHEMA,
        "track_path": str(track_path),
        "spectrum": {
            "mono_target_rate_hz": _MONO_TARGET_RATE_HZ,
            "hop_ms": int(hop_ms),
            "band_count": int(band_count),
            "max_frames": int(max_frames),
        },
    }
    if waveform_hop_ms is not None and max_waveform_frames is not None:
        request_payload["waveform_proxy"] = {
            "hop_ms": int(waveform_hop_ms),
            "max_frames": int(max_waveform_frames),
        }
        # Duplicate these with unique top-level keys for simple/naive helper parsers.
        request_payload["waveform_proxy_hop_ms"] = int(waveform_hop_ms)
        request_payload["waveform_proxy_max_frames"] = int(max_waveform_frames)
    if beat_hop_ms is not None and max_beat_frames is not None:
        request_payload["beat"] = {
            "hop_ms": int(beat_hop_ms),
            "max_frames": int(max_beat_frames),
        }
        # Duplicate these with unique top-level keys for simple/naive helper parsers.
        request_payload["beat_timeline_hop_ms"] = int(beat_hop_ms)
        request_payload["beat_timeline_max_frames"] = int(max_beat_frames)
    try:
        proc = subprocess.run(
            list(config.argv),
            input=json.dumps(request_payload).encode("utf-8"),
            capture_output=True,
            check=False,
            timeout=config.timeout_s,
        )
    except subprocess.TimeoutExpired:
        return NativeSpectrumHelperAttempt(
            result=None, failure_reason="native_helper_timeout"
        )
    except (OSError, subprocess.SubprocessError):
        return NativeSpectrumHelperAttempt(
            result=None, failure_reason="native_helper_invocation_error"
        )
    if proc.returncode != 0 or not proc.stdout:
        if proc.returncode != 0:
            return NativeSpectrumHelperAttempt(
                result=None, failure_reason="native_helper_nonzero_exit"
            )
        return NativeSpectrumHelperAttempt(
            result=None, failure_reason="native_helper_empty_output"
        )

    try:
        payload = json.loads(proc.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return NativeSpectrumHelperAttempt(
            result=None, failure_reason="native_helper_invalid_json"
        )
    parsed = _parse_helper_response(payload)
    if parsed is None:
        return NativeSpectrumHelperAttempt(
            result=None, failure_reason="native_helper_invalid_output"
        )
    return NativeSpectrumHelperAttempt(result=parsed, failure_reason=None)


def _parse_timeout_s(raw: str | None) -> float:
    if raw is None:
        return _DEFAULT_HELPER_TIMEOUT_S
    try:
        parsed = float(raw)
    except ValueError:
        return _DEFAULT_HELPER_TIMEOUT_S
    return max(0.1, parsed)


def _parse_helper_response(payload: object) -> NativeSpectrumHelperResult | None:
    if not isinstance(payload, dict):
        return None
    if payload.get("schema") != _RESPONSE_SCHEMA:
        return None
    duration_ms = payload.get("duration_ms")
    raw_frames = payload.get("frames")
    if not isinstance(duration_ms, int) or duration_ms <= 0:
        return None
    frames = _parse_frames(raw_frames)
    if frames is None:
        return None

    timings_payload = payload.get("timings")
    timings = _parse_timings(timings_payload)
    helper_version = payload.get("helper_version")
    if helper_version is not None and not isinstance(helper_version, str):
        helper_version = None

    return NativeSpectrumHelperResult(
        spectrum=SpectrumAnalysisResult(duration_ms=duration_ms, frames=frames),
        beat=_parse_beat(payload.get("beat")),
        waveform_proxy=_parse_waveform_proxy(payload.get("waveform_proxy")),
        timings=timings,
        helper_version=helper_version,
    )


def _parse_frames(raw_frames: object) -> list[tuple[int, bytes]] | None:
    if not isinstance(raw_frames, list) or not raw_frames:
        return None
    parsed: list[tuple[int, bytes]] = []
    for item in raw_frames:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or not isinstance(item[0], int)
            or item[0] < 0
            or not isinstance(item[1], list)
        ):
            return None
        try:
            bands = bytes(int(value) for value in item[1])
        except (TypeError, ValueError):
            return None
        if len(bands) != len(item[1]):
            return None
        parsed.append((item[0], bands))
    return parsed or None


def _parse_timings(raw_timings: object) -> NativeSpectrumHelperTimingBreakdown | None:
    if raw_timings is None:
        return None
    if not isinstance(raw_timings, dict):
        return None
    return NativeSpectrumHelperTimingBreakdown(
        decode_ms=_coerce_optional_float(raw_timings.get("decode_ms")),
        spectrum_ms=_coerce_optional_float(raw_timings.get("spectrum_ms")),
        beat_ms=_coerce_optional_float(raw_timings.get("beat_ms")),
        waveform_proxy_ms=_coerce_optional_float(raw_timings.get("waveform_proxy_ms")),
        total_ms=_coerce_optional_float(raw_timings.get("total_ms")),
    )


def _parse_beat(raw_beat: object) -> BeatAnalysisResult | None:
    if raw_beat is None:
        return None
    if not isinstance(raw_beat, dict):
        return None
    duration_ms = raw_beat.get("duration_ms")
    bpm = raw_beat.get("bpm")
    raw_frames = raw_beat.get("frames")
    if not isinstance(duration_ms, int) or duration_ms <= 0:
        return None
    if not isinstance(bpm, (int, float)):
        return None
    if not isinstance(raw_frames, list) or not raw_frames:
        return None
    frames: list[tuple[int, int, bool]] = []
    for item in raw_frames:
        if (
            not isinstance(item, list)
            or len(item) != 3
            or not isinstance(item[0], int)
            or item[0] < 0
            or not isinstance(item[1], int)
            or not isinstance(item[2], bool)
        ):
            return None
        pos_ms, strength_u8, is_beat = item
        if strength_u8 < 0 or strength_u8 > 255:
            return None
        frames.append((pos_ms, strength_u8, is_beat))
    return BeatAnalysisResult(duration_ms=duration_ms, bpm=float(bpm), frames=frames)


def _parse_waveform_proxy(raw_waveform: object) -> WaveformProxyAnalysisResult | None:
    if raw_waveform is None:
        return None
    if not isinstance(raw_waveform, dict):
        return None
    duration_ms = raw_waveform.get("duration_ms")
    raw_frames = raw_waveform.get("frames")
    if not isinstance(duration_ms, int) or duration_ms <= 0:
        return None
    if not isinstance(raw_frames, list) or not raw_frames:
        return None
    frames: list[tuple[int, int, int, int, int]] = []
    for item in raw_frames:
        if (
            not isinstance(item, list)
            or len(item) != 5
            or not all(isinstance(value, int) for value in item)
        ):
            return None
        pos_ms, lmin, lmax, rmin, rmax = item
        if pos_ms < 0:
            return None
        frames.append((pos_ms, lmin, lmax, rmin, rmax))
    return WaveformProxyAnalysisResult(duration_ms=duration_ms, frames=frames)


def _coerce_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None
