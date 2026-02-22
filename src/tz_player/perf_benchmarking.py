"""Opt-in performance benchmark result schema and helper utilities.

This module defines a stable, JSON-serializable contract for opt-in benchmark
results so future perf scenarios can be compared across commits/branches.
"""

from __future__ import annotations

import json
import math
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import TypeAlias

PERF_RESULT_SCHEMA_VERSION = 1

SCENARIO_COLD_CACHE_TRACK_PLAY = "cold_cache_track_play"
SCENARIO_WARM_CACHE_TRACK_PLAY = "warm_cache_track_play"
SCENARIO_RAPID_TRACK_SWITCH_BURST = "rapid_track_switch_burst"
SCENARIO_LONG_TRACK_ANALYSIS_ON_DEMAND = "long_track_analysis_on_demand"
SCENARIO_VISUALIZER_MATRIX_RENDER = "visualizer_matrix_render"
SCENARIO_CONTROLS_INTERACTION_LATENCY = "controls_interaction_latency"
SCENARIO_LARGE_PLAYLIST_DB_QUERY_MATRIX = "large_playlist_db_query_matrix"
SCENARIO_HIDDEN_HOTSPOT_IDLE_PLAYBACK_SWEEP = "hidden_hotspot_idle_playback_sweep"
SCENARIO_HIDDEN_HOTSPOT_BROWSE_SWEEP = "hidden_hotspot_browse_sweep"

PERF_SCENARIO_IDS: tuple[str, ...] = (
    SCENARIO_COLD_CACHE_TRACK_PLAY,
    SCENARIO_WARM_CACHE_TRACK_PLAY,
    SCENARIO_RAPID_TRACK_SWITCH_BURST,
    SCENARIO_LONG_TRACK_ANALYSIS_ON_DEMAND,
    SCENARIO_VISUALIZER_MATRIX_RENDER,
    SCENARIO_CONTROLS_INTERACTION_LATENCY,
    SCENARIO_LARGE_PLAYLIST_DB_QUERY_MATRIX,
    SCENARIO_HIDDEN_HOTSPOT_IDLE_PLAYBACK_SWEEP,
    SCENARIO_HIDDEN_HOTSPOT_BROWSE_SWEEP,
)

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


def utc_now_iso() -> str:
    """Return current UTC timestamp formatted as an ISO-8601 `Z` string."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _percentile(sorted_samples: list[float], p: float) -> float:
    """Return percentile using linear interpolation on sorted samples."""
    if not sorted_samples:
        raise ValueError("samples must not be empty")
    if len(sorted_samples) == 1:
        return sorted_samples[0]
    rank = (len(sorted_samples) - 1) * p
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return sorted_samples[lower]
    fraction = rank - lower
    return sorted_samples[lower] + (sorted_samples[upper] - sorted_samples[lower]) * (
        fraction
    )


@dataclass(frozen=True)
class PerfMetricSummary:
    """Aggregated benchmark metric summary."""

    unit: str
    count: int
    min_value: float
    median_value: float
    p95_value: float
    max_value: float
    mean_value: float


def summarize_samples(samples: list[float], *, unit: str) -> PerfMetricSummary:
    """Summarize numeric samples for benchmark output."""
    if not samples:
        raise ValueError("samples must not be empty")
    sorted_samples = sorted(float(value) for value in samples)
    return PerfMetricSummary(
        unit=unit,
        count=len(sorted_samples),
        min_value=sorted_samples[0],
        median_value=_percentile(sorted_samples, 0.5),
        p95_value=_percentile(sorted_samples, 0.95),
        max_value=sorted_samples[-1],
        mean_value=statistics.fmean(sorted_samples),
    )


@dataclass(frozen=True)
class PerfScenarioResult:
    """Result payload for one benchmark scenario."""

    scenario_id: str
    category: str
    status: str
    elapsed_s: float
    metrics: dict[str, PerfMetricSummary] = field(default_factory=dict)
    counters: dict[str, JsonScalar] = field(default_factory=dict)
    metadata: dict[str, JsonValue] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, JsonValue]:
        payload = asdict(self)
        return payload


@dataclass(frozen=True)
class PerfRunResult:
    """Top-level benchmark run artifact."""

    run_id: str
    created_at: str
    app_version: str | None
    git_sha: str | None
    machine: dict[str, JsonValue]
    config: dict[str, JsonValue]
    scenarios: list[PerfScenarioResult]
    schema_version: int = PERF_RESULT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "created_at": self.created_at,
            "app_version": self.app_version,
            "git_sha": self.git_sha,
            "machine": self.machine,
            "config": self.config,
            "scenarios": [scenario.to_dict() for scenario in self.scenarios],
        }

    def to_json(self) -> str:
        """Serialize benchmark artifact to canonical JSON text."""
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=True)


def validate_perf_run_payload(payload: dict[str, JsonValue]) -> list[str]:
    """Return schema validation errors for a benchmark payload.

    This is intentionally lightweight (no external schema dependency) and is
    suitable for opt-in tests and local tooling.
    """
    errors: list[str] = []
    if not isinstance(payload.get("schema_version"), int):
        errors.append("schema_version must be int")
    if not isinstance(payload.get("run_id"), str) or not payload["run_id"]:
        errors.append("run_id must be non-empty string")
    if not isinstance(payload.get("created_at"), str):
        errors.append("created_at must be string")
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list):
        errors.append("scenarios must be list")
        return errors
    for index, scenario in enumerate(scenarios):
        if not isinstance(scenario, dict):
            errors.append(f"scenarios[{index}] must be object")
            continue
        scenario_id = scenario.get("scenario_id")
        if not isinstance(scenario_id, str) or not scenario_id:
            errors.append(f"scenarios[{index}].scenario_id must be non-empty string")
        status = scenario.get("status")
        if status not in {"pass", "fail", "skip", "error"}:
            errors.append(
                f"scenarios[{index}].status must be one of pass|fail|skip|error"
            )
        elapsed_s = scenario.get("elapsed_s")
        if not isinstance(elapsed_s, (int, float)) or elapsed_s < 0:
            errors.append(f"scenarios[{index}].elapsed_s must be non-negative number")
        metrics = scenario.get("metrics")
        if not isinstance(metrics, dict):
            errors.append(f"scenarios[{index}].metrics must be object")
            continue
        for metric_name, metric in metrics.items():
            if not isinstance(metric_name, str) or not metric_name:
                errors.append(
                    f"scenarios[{index}].metrics keys must be non-empty strings"
                )
                continue
            if not isinstance(metric, dict):
                errors.append(
                    f"scenarios[{index}].metrics[{metric_name!r}] must be object"
                )
                continue
            if not isinstance(metric.get("unit"), str):
                errors.append(
                    f"scenarios[{index}].metrics[{metric_name!r}].unit must be string"
                )
            count = metric.get("count")
            if not isinstance(count, int) or count < 0:
                errors.append(
                    f"scenarios[{index}].metrics[{metric_name!r}].count must be >= 0 int"
                )
    return errors
