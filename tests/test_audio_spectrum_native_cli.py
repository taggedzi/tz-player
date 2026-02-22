"""Tests for optional native spectrum CLI helper adapter."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from tz_player.services.audio_spectrum_native_cli import (
    NATIVE_SPECTRUM_HELPER_CMD_ENV,
    NATIVE_SPECTRUM_HELPER_TIMEOUT_ENV,
    analyze_track_spectrum_via_native_cli,
    analyze_track_spectrum_via_native_cli_attempt,
    get_native_spectrum_helper_config,
)


def test_get_native_spectrum_helper_config_disabled_by_default() -> None:
    assert get_native_spectrum_helper_config({}) is None


def test_get_native_spectrum_helper_config_parses_command_and_timeout() -> None:
    cfg = get_native_spectrum_helper_config(
        {
            NATIVE_SPECTRUM_HELPER_CMD_ENV: "helper-bin --mode poc",
            NATIVE_SPECTRUM_HELPER_TIMEOUT_ENV: "2.5",
        }
    )
    assert cfg is not None
    assert cfg.argv == ("helper-bin", "--mode", "poc")
    assert cfg.timeout_s == 2.5


def test_get_native_spectrum_helper_config_preserves_windows_path_backslashes(
    monkeypatch,
) -> None:
    monkeypatch.setattr(os, "name", "nt", raising=False)
    cfg = get_native_spectrum_helper_config(
        {
            NATIVE_SPECTRUM_HELPER_CMD_ENV: r"C:\Users\tagge\AppData\Local\Temp\native_spectrum_helper_c_poc.exe",
        }
    )
    assert cfg is not None
    assert cfg.argv == (
        r"C:\Users\tagge\AppData\Local\Temp\native_spectrum_helper_c_poc.exe",
    )


def test_analyze_track_spectrum_via_native_cli_parses_response(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        captured["cmd"] = cmd
        captured["input"] = kwargs.get("input")
        payload = {
            "schema": "tz_player.native_spectrum_helper_response.v1",
            "duration_ms": 1000,
            "frames": [[0, [1, 2, 3, 255]], [40, [4, 5, 6, 7]]],
            "beat": {
                "duration_ms": 1000,
                "bpm": 120.0,
                "frames": [[0, 0, False], [40, 128, True]],
            },
            "waveform_proxy": {
                "duration_ms": 1000,
                "frames": [[0, -10, 10, -8, 8]],
            },
            "timings": {
                "decode_ms": 1.2,
                "spectrum_ms": 3.4,
                "beat_ms": 0.7,
                "waveform_proxy_ms": 0.9,
                "total_ms": 5.6,
            },
            "helper_version": "dev-cli",
        }
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout=json.dumps(payload).encode("utf-8"),
            stderr=b"",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = analyze_track_spectrum_via_native_cli(
        Path("/tmp/test.wav"),
        band_count=4,
        hop_ms=40,
        max_frames=100,
        waveform_hop_ms=20,
        max_waveform_frames=200,
        beat_hop_ms=40,
        max_beat_frames=300,
        env={NATIVE_SPECTRUM_HELPER_CMD_ENV: "native-helper"},
    )

    assert result is not None
    assert list(captured["cmd"]) == ["native-helper"]
    request = json.loads((captured["input"] or b"").decode("utf-8"))
    assert request["track_path"] == "/tmp/test.wav"
    assert request["spectrum"]["band_count"] == 4
    assert request["beat_timeline_hop_ms"] == 40
    assert request["beat_timeline_max_frames"] == 300
    assert request["waveform_proxy_hop_ms"] == 20
    assert request["waveform_proxy_max_frames"] == 200
    assert result.spectrum.duration_ms == 1000
    assert result.spectrum.frames[0] == (0, bytes([1, 2, 3, 255]))
    assert result.beat is not None
    assert result.beat.bpm == 120.0
    assert result.beat.frames[1] == (40, 128, True)
    assert result.waveform_proxy is not None
    assert result.waveform_proxy.frames == [(0, -10, 10, -8, 8)]
    assert result.timings is not None
    assert result.timings.decode_ms == 1.2
    assert result.timings.beat_ms == 0.7
    assert result.timings.waveform_proxy_ms == 0.9
    assert result.helper_version == "dev-cli"


def test_analyze_track_spectrum_via_native_cli_falls_back_on_bad_payload(
    monkeypatch,
) -> None:
    def fake_run(cmd, **kwargs):  # noqa: ANN001, ARG001
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout=b'{"schema":"wrong"}',
            stderr=b"",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = analyze_track_spectrum_via_native_cli(
        "song.wav",
        band_count=8,
        hop_ms=40,
        max_frames=100,
        env={NATIVE_SPECTRUM_HELPER_CMD_ENV: "native-helper"},
    )
    assert result is None


def test_analyze_track_spectrum_via_native_cli_attempt_reports_timeout(
    monkeypatch,
) -> None:
    def fake_run(cmd, **kwargs):  # noqa: ANN001, ARG001
        raise subprocess.TimeoutExpired(cmd=["native-helper"], timeout=1.0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    attempt = analyze_track_spectrum_via_native_cli_attempt(
        "song.wav",
        band_count=8,
        hop_ms=40,
        max_frames=100,
        env={NATIVE_SPECTRUM_HELPER_CMD_ENV: "native-helper"},
    )
    assert attempt.result is None
    assert attempt.failure_reason == "native_helper_timeout"
