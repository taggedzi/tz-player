"""Smoke tests for the native spectrum helper stub CLI."""

from __future__ import annotations

import json
import math
import subprocess
import sys
import wave
from pathlib import Path


def _write_wave(path: Path, *, frames: int = 22_050, sample_rate: int = 44_100) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        payload = bytearray()
        for idx in range(frames):
            left = int(18000 * math.sin((2.0 * math.pi * 220.0 * idx) / sample_rate))
            right = int(9000 * math.sin((2.0 * math.pi * 440.0 * idx) / sample_rate))
            payload.extend(left.to_bytes(2, "little", signed=True))
            payload.extend(right.to_bytes(2, "little", signed=True))
        handle.writeframes(bytes(payload))


def test_native_spectrum_helper_stub_returns_valid_payload(tmp_path) -> None:
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
    }

    proc = subprocess.run(
        [sys.executable, "tools/native_spectrum_helper_stub.py"],
        input=json.dumps(request).encode("utf-8"),
        capture_output=True,
        check=False,
        cwd=Path(__file__).resolve().parents[1],
    )

    assert proc.returncode == 0, proc.stderr.decode("utf-8", errors="ignore")
    payload = json.loads(proc.stdout.decode("utf-8"))
    assert payload["schema"] == "tz_player.native_spectrum_helper_response.v1"
    assert payload["helper_version"] == "stub-python-cli-v1"
    assert payload["duration_ms"] > 0
    assert payload["frames"]
    assert isinstance(payload["frames"][0][0], int)
    assert isinstance(payload["frames"][0][1], list)
    assert payload["timings"]["total_ms"] >= 0
