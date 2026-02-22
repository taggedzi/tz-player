from __future__ import annotations

import json
from pathlib import Path

import pytest

from tz_player.perf_benchmarking import (
    PERF_MEDIA_DIR_ENV,
    PERF_RESULT_SCHEMA_VERSION,
    PERF_SCENARIO_IDS,
    PerfRunResult,
    PerfScenarioResult,
    build_perf_media_manifest,
    perf_media_skip_reason,
    resolve_perf_media_dir,
    summarize_samples,
    utc_now_iso,
    validate_perf_run_payload,
)


def test_summarize_samples_computes_summary_stats() -> None:
    metric = summarize_samples([10.0, 20.0, 30.0, 40.0, 50.0], unit="ms")
    assert metric.unit == "ms"
    assert metric.count == 5
    assert metric.min_value == 10.0
    assert metric.median_value == 30.0
    assert metric.max_value == 50.0
    assert metric.mean_value == 30.0
    assert 40.0 <= metric.p95_value <= 50.0


def test_summarize_samples_rejects_empty_samples() -> None:
    with pytest.raises(ValueError, match="samples must not be empty"):
        summarize_samples([], unit="ms")


def test_perf_run_result_serializes_to_valid_json_payload() -> None:
    scenario = PerfScenarioResult(
        scenario_id="warm_cache_track_play",
        category="track_switch",
        status="pass",
        elapsed_s=0.123,
        metrics={"switch_latency_ms": summarize_samples([10.0, 12.0, 14.0], unit="ms")},
        counters={"track_count": 3},
        metadata={"profile": "balanced"},
        notes=["warm cache"],
    )
    run = PerfRunResult(
        run_id="run-001",
        created_at=utc_now_iso(),
        app_version="0.0-test",
        git_sha="deadbeef",
        machine={"os": "linux"},
        config={"profile": "balanced"},
        scenarios=[scenario],
    )

    payload = run.to_dict()
    assert payload["schema_version"] == PERF_RESULT_SCHEMA_VERSION
    assert json.loads(run.to_json())["run_id"] == "run-001"
    assert validate_perf_run_payload(payload) == []


def test_validate_perf_run_payload_reports_missing_fields() -> None:
    payload = {
        "schema_version": 1,
        "run_id": "x",
        "created_at": "2026-02-22T00:00:00Z",
        "scenarios": [
            {
                "scenario_id": "",
                "status": "ok",
                "elapsed_s": -1,
                "metrics": {"m": {"unit": 5, "count": -1}},
            }
        ],
    }

    errors = validate_perf_run_payload(payload)
    assert any("scenario_id" in error for error in errors)
    assert any(".status" in error for error in errors)
    assert any(".elapsed_s" in error for error in errors)
    assert any(".unit" in error for error in errors)
    assert any(".count" in error for error in errors)


def test_perf_scenario_catalog_includes_hidden_hotspot_sweeps() -> None:
    assert "hidden_hotspot_idle_playback_sweep" in PERF_SCENARIO_IDS
    assert "hidden_hotspot_browse_sweep" in PERF_SCENARIO_IDS
    assert "visualizer_matrix_render" in PERF_SCENARIO_IDS


def test_resolve_perf_media_dir_uses_default_if_present(tmp_path: Path) -> None:
    perf_dir = tmp_path / ".local" / "perf_media"
    perf_dir.mkdir(parents=True)

    resolved = resolve_perf_media_dir(cwd=tmp_path, env={})
    assert resolved == perf_dir.resolve()


def test_resolve_perf_media_dir_prefers_env_override(tmp_path: Path) -> None:
    explicit = tmp_path / "custom_media"
    explicit.mkdir()

    resolved = resolve_perf_media_dir(
        cwd=tmp_path, env={PERF_MEDIA_DIR_ENV: str(explicit)}
    )
    assert resolved == explicit.resolve()


def test_perf_media_skip_reason_and_manifest(tmp_path: Path) -> None:
    media_dir = tmp_path / ".local" / "perf_media"
    media_dir.mkdir(parents=True)
    assert (
        perf_media_skip_reason(media_dir)
        == f"Perf media corpus directory is empty: {media_dir}"
    )

    (media_dir / "a.mp3").write_bytes(b"abc")
    nested = media_dir / "nested"
    nested.mkdir()
    (nested / "b.flac").write_bytes(b"12345")
    (nested / "ignore.txt").write_text("x", encoding="utf-8")

    assert perf_media_skip_reason(media_dir) is None
    manifest = build_perf_media_manifest(media_dir, probe_durations=False)
    assert manifest["track_count"] == 2
    assert manifest["total_bytes"] == 8
    assert manifest["formats"] == {"flac": 1, "mp3": 1}
    assert manifest["duration_probe_mode"] == "disabled"
