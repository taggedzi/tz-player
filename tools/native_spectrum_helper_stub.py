#!/usr/bin/env python3
"""Stub CLI helper for native-spectrum POC plumbing.

Reads a JSON request from stdin and writes a JSON response compatible with
`audio_spectrum_native_cli.py`. This stub intentionally uses the existing
Python analysis path so we can validate integration and benchmark metadata
before introducing real native code.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

REQUEST_SCHEMA = "tz_player.native_spectrum_helper_request.v1"
RESPONSE_SCHEMA = "tz_player.native_spectrum_helper_response.v1"


def main() -> int:
    from tz_player.services.audio_spectrum_analysis import (
        analyze_track_spectrum,
    )

    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"invalid json request: {exc}", file=sys.stderr)
        return 2

    if not isinstance(payload, dict) or payload.get("schema") != REQUEST_SCHEMA:
        print("invalid request schema", file=sys.stderr)
        return 2
    track_path = payload.get("track_path")
    spectrum = payload.get("spectrum")
    if not isinstance(track_path, str) or not isinstance(spectrum, dict):
        print("missing request fields", file=sys.stderr)
        return 2

    try:
        band_count = int(spectrum.get("band_count", 48))
        hop_ms = int(spectrum.get("hop_ms", 40))
        max_frames = int(spectrum.get("max_frames", 12_000))
    except (TypeError, ValueError):
        print("invalid spectrum config fields", file=sys.stderr)
        return 2

    total_start = time.perf_counter()
    # Stub helper cannot separate decode and spectrum timings because it
    # intentionally calls the current Python combined path.
    result = analyze_track_spectrum(
        track_path,
        band_count=band_count,
        hop_ms=hop_ms,
        max_frames=max_frames,
    )
    total_ms = (time.perf_counter() - total_start) * 1000.0
    if result is None:
        print("analysis failed", file=sys.stderr)
        return 1

    response = {
        "schema": RESPONSE_SCHEMA,
        "helper_version": "stub-python-cli-v1",
        "duration_ms": result.duration_ms,
        "frames": [[pos_ms, list(bands)] for pos_ms, bands in result.frames],
        "timings": {
            "decode_ms": None,
            "spectrum_ms": round(total_ms, 3),
            "total_ms": round(total_ms, 3),
        },
    }
    sys.stdout.write(json.dumps(response))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
