"""Smoke tests for the compiled native spectrum helper C POC."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import wave
from pathlib import Path

import pytest


def _write_wave(path: Path, *, frames: int = 22_050, sample_rate: int = 44_100) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        payload = bytearray()
        for idx in range(frames):
            left = int(16000 * math.sin((2.0 * math.pi * 220.0 * idx) / sample_rate))
            right = int(10000 * math.sin((2.0 * math.pi * 440.0 * idx) / sample_rate))
            payload.extend(left.to_bytes(2, "little", signed=True))
            payload.extend(right.to_bytes(2, "little", signed=True))
        handle.writeframes(bytes(payload))


@pytest.mark.skipif(shutil.which("gcc") is None, reason="gcc not available")
def test_native_spectrum_helper_c_poc_compiles_and_returns_valid_payload(tmp_path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    bin_path = tmp_path / "native_spectrum_helper_c_poc"
    subprocess.run(
        ["bash", "tools/build_native_spectrum_helper_c_poc.sh", str(bin_path)],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    track = tmp_path / "tone.wav"
    _write_wave(track)
    request = {
        "schema": "tz_player.native_spectrum_helper_request.v1",
        "track_path": str(track),
        "spectrum": {
            "mono_target_rate_hz": 11025,
            "hop_ms": 40,
            "band_count": 8,
            "max_frames": 100,
        },
        "beat_timeline_hop_ms": 40,
        "beat_timeline_max_frames": 100,
        "waveform_proxy_hop_ms": 20,
        "waveform_proxy_max_frames": 200,
    }
    proc = subprocess.run(
        [str(bin_path)],
        input=json.dumps(request).encode("utf-8"),
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", errors="ignore")
    payload = json.loads(proc.stdout.decode("utf-8"))
    assert payload["schema"] == "tz_player.native_spectrum_helper_response.v1"
    assert payload["helper_version"] == "c-poc-ffmpeg-v2"
    assert payload["duration_ms"] > 0
    assert payload["frames"]
    assert len(payload["frames"][0][1]) == 8
    assert payload["beat"]["frames"]
    assert payload["waveform_proxy"]["frames"]
    assert payload["timings"]["total_ms"] >= 0


@pytest.mark.skipif(shutil.which("gcc") is None, reason="gcc not available")
def test_native_spectrum_helper_c_poc_accepts_nested_request_objects(tmp_path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    bin_path = tmp_path / "native_spectrum_helper_c_poc"
    subprocess.run(
        ["bash", "tools/build_native_spectrum_helper_c_poc.sh", str(bin_path)],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    track = tmp_path / "tone.wav"
    _write_wave(track, frames=44_100)
    request = {
        "schema": "tz_player.native_spectrum_helper_request.v1",
        "track_path": str(track),
        # Put beat/waveform before spectrum to verify nested parsing avoids key ambiguity.
        "beat": {"hop_ms": 40, "max_frames": 100},
        "waveform_proxy": {"hop_ms": 25, "max_frames": 200},
        "spectrum": {
            "mono_target_rate_hz": 11025,
            "hop_ms": 80,
            "band_count": 8,
            "max_frames": 100,
        },
    }
    proc = subprocess.run(
        [str(bin_path)],
        input=json.dumps(request).encode("utf-8"),
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", errors="ignore")
    payload = json.loads(proc.stdout.decode("utf-8"))
    assert payload["frames"]
    assert payload["beat"]["frames"]
    assert payload["waveform_proxy"]["frames"]
    # Nested-only request objects should be honored, not confused by global hop_ms lookup.
    assert payload["frames"][1][0] == 80
    assert payload["beat"]["frames"][1][0] == 40
    assert payload["waveform_proxy"]["frames"][1][0] in {24, 25}


@pytest.mark.skipif(
    shutil.which("gcc") is None or shutil.which("ffmpeg") is None,
    reason="gcc and ffmpeg required",
)
def test_native_spectrum_helper_c_poc_supports_mp3_via_ffmpeg(tmp_path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    bin_path = tmp_path / "native_spectrum_helper_c_poc"
    subprocess.run(
        ["bash", "tools/build_native_spectrum_helper_c_poc.sh", str(bin_path)],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    wav_path = tmp_path / "tone source.wav"
    mp3_path = tmp_path / "tone's sample.mp3"
    _write_wave(wav_path)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(wav_path), str(mp3_path)],
        check=True,
        capture_output=True,
    )
    request = {
        "schema": "tz_player.native_spectrum_helper_request.v1",
        "track_path": str(mp3_path),
        "spectrum": {
            "mono_target_rate_hz": 11025,
            "hop_ms": 40,
            "band_count": 8,
            "max_frames": 100,
        },
        "beat_timeline_hop_ms": 40,
        "beat_timeline_max_frames": 100,
        "waveform_proxy_hop_ms": 20,
        "waveform_proxy_max_frames": 200,
    }
    proc = subprocess.run(
        [str(bin_path)],
        input=json.dumps(request).encode("utf-8"),
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", errors="ignore")
    payload = json.loads(proc.stdout.decode("utf-8"))
    assert payload["schema"] == "tz_player.native_spectrum_helper_response.v1"
    assert payload["helper_version"] == "c-poc-ffmpeg-v2"
    assert payload["frames"]
    assert payload["beat"]["frames"]
    assert payload["waveform_proxy"]["frames"]
