"""Opt-in performance benchmark result schema and helper utilities.

This module defines a stable, JSON-serializable contract for opt-in benchmark
results so future perf scenarios can be compared across commits/branches.
"""

from __future__ import annotations

import json
import math
import os
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeAlias

PERF_RESULT_SCHEMA_VERSION = 1
PERF_MEDIA_DIR_ENV = "TZ_PLAYER_PERF_MEDIA_DIR"
PERF_RESULTS_DIR_ENV = "TZ_PLAYER_PERF_RESULTS_DIR"
DEFAULT_LOCAL_PERF_MEDIA_DIR = Path(".local/perf_media")
DEFAULT_LOCAL_PERF_RESULTS_DIR = Path(".local/perf_results")
PERF_MEDIA_AUDIO_SUFFIXES = frozenset(
    {".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".opus", ".wma"}
)

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


def resolve_perf_media_dir(
    *, cwd: Path | None = None, env: dict[str, str] | None = None
) -> Path | None:
    """Resolve local perf media corpus directory from env or default path."""
    if env is None:
        env = os.environ
    if cwd is None:
        cwd = Path.cwd()
    explicit = env.get(PERF_MEDIA_DIR_ENV)
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_absolute():
            path = (cwd / path).resolve()
        return path
    candidate = (cwd / DEFAULT_LOCAL_PERF_MEDIA_DIR).resolve()
    if candidate.exists():
        return candidate
    return None


def resolve_perf_results_dir(
    *, cwd: Path | None = None, env: dict[str, str] | None = None
) -> Path:
    """Resolve local perf benchmark results directory path."""
    if env is None:
        env = os.environ
    if cwd is None:
        cwd = Path.cwd()
    explicit = env.get(PERF_RESULTS_DIR_ENV)
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_absolute():
            path = (cwd / path).resolve()
        return path
    return (cwd / DEFAULT_LOCAL_PERF_RESULTS_DIR).resolve()


def perf_media_skip_reason(media_dir: Path | None) -> str | None:
    """Return a skip reason if local perf corpus is unavailable/unusable."""
    if media_dir is None:
        return (
            "No local perf media corpus found. Set "
            f"{PERF_MEDIA_DIR_ENV}=<path> or create .local/perf_media/."
        )
    if not media_dir.exists():
        return f"Perf media corpus path does not exist: {media_dir}"
    if not media_dir.is_dir():
        return f"Perf media corpus path is not a directory: {media_dir}"
    audio_files = [path for path in media_dir.rglob("*") if path.is_file()]
    if not audio_files:
        return f"Perf media corpus directory is empty: {media_dir}"
    return None


def _audio_files_under(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in PERF_MEDIA_AUDIO_SUFFIXES
    )


def _best_effort_duration_seconds(path: Path) -> float | None:
    try:
        from mutagen import File as MutagenFile
    except Exception:
        return None
    try:
        parsed = MutagenFile(path)
    except Exception:
        return None
    if parsed is None or getattr(parsed, "info", None) is None:
        return None
    length = getattr(parsed.info, "length", None)
    if isinstance(length, (int, float)) and length >= 0:
        return float(length)
    return None


def build_perf_media_manifest(
    media_dir: Path, *, probe_durations: bool = False, duration_probe_limit: int = 200
) -> dict[str, JsonValue]:
    """Build a reproducibility manifest for a local perf media corpus."""
    audio_files = _audio_files_under(media_dir)
    suffix_counts: dict[str, int] = {}
    total_bytes = 0
    for path in audio_files:
        suffix = path.suffix.lower().lstrip(".") or "unknown"
        suffix_counts[suffix] = suffix_counts.get(suffix, 0) + 1
        total_bytes += path.stat().st_size

    manifest: dict[str, JsonValue] = {
        "root": str(media_dir),
        "track_count": len(audio_files),
        "total_bytes": total_bytes,
        "formats": dict(sorted(suffix_counts.items())),
    }
    if not probe_durations:
        manifest["duration_probe_mode"] = "disabled"
        return manifest

    duration_total = 0.0
    probed = 0
    missing = 0
    for path in audio_files[: max(0, duration_probe_limit)]:
        duration = _best_effort_duration_seconds(path)
        if duration is None:
            missing += 1
            continue
        duration_total += duration
        probed += 1
    manifest["duration_probe_mode"] = "mutagen_best_effort"
    manifest["duration_probe_limit"] = max(0, duration_probe_limit)
    manifest["duration_probed_count"] = probed
    manifest["duration_missing_count"] = missing
    manifest["duration_total_s"] = round(duration_total, 3)
    return manifest


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


@dataclass(frozen=True)
class PerfMetricDelta:
    """Comparison of one scenario metric between two benchmark runs."""

    scenario_id: str
    metric_name: str
    unit: str
    baseline_median: float
    candidate_median: float
    delta_median: float
    pct_median: float | None
    baseline_p95: float
    candidate_p95: float
    delta_p95: float
    pct_p95: float | None


@dataclass(frozen=True)
class PerfComparisonResult:
    """Structured comparison output for two perf benchmark runs."""

    baseline_run_id: str
    candidate_run_id: str
    comparable_metric_count: int
    regressed_metrics: list[PerfMetricDelta]
    improved_metrics: list[PerfMetricDelta]
    unchanged_metrics: list[PerfMetricDelta]
    missing_in_candidate: list[str]
    new_in_candidate: list[str]


def _safe_pct(delta: float, baseline: float) -> float | None:
    if baseline == 0:
        return None
    return (delta / baseline) * 100.0


def _scenario_metric_key(scenario_id: str, metric_name: str) -> str:
    return f"{scenario_id}.{metric_name}"


def _flatten_run_metrics(
    payload: dict[str, JsonValue],
) -> dict[str, dict[str, JsonValue]]:
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list):
        return {}
    flat: dict[str, dict[str, JsonValue]] = {}
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            continue
        scenario_id = scenario.get("scenario_id")
        metrics = scenario.get("metrics")
        if not isinstance(scenario_id, str) or not isinstance(metrics, dict):
            continue
        for metric_name, metric in metrics.items():
            if not isinstance(metric_name, str) or not isinstance(metric, dict):
                continue
            flat[_scenario_metric_key(scenario_id, metric_name)] = metric
    return flat


def compare_perf_run_payloads(
    baseline: dict[str, JsonValue],
    candidate: dict[str, JsonValue],
    *,
    regression_pct_threshold: float = 5.0,
    improvement_pct_threshold: float = -5.0,
) -> PerfComparisonResult:
    """Compare two perf benchmark payloads using metric median/p95 values.

    Positive deltas/percentages indicate slower/larger values in the candidate
    run and are treated as regressions for latency-like metrics. This assumes
    metric values are "lower is better".
    """
    base_flat = _flatten_run_metrics(baseline)
    cand_flat = _flatten_run_metrics(candidate)
    base_keys = set(base_flat)
    cand_keys = set(cand_flat)
    shared_keys = sorted(base_keys & cand_keys)

    regressed: list[PerfMetricDelta] = []
    improved: list[PerfMetricDelta] = []
    unchanged: list[PerfMetricDelta] = []

    for key in shared_keys:
        base_metric = base_flat[key]
        cand_metric = cand_flat[key]
        base_unit = base_metric.get("unit")
        cand_unit = cand_metric.get("unit")
        if not isinstance(base_unit, str) or not isinstance(cand_unit, str):
            continue
        if base_unit != cand_unit:
            continue
        base_med = base_metric.get("median_value")
        cand_med = cand_metric.get("median_value")
        base_p95 = base_metric.get("p95_value")
        cand_p95 = cand_metric.get("p95_value")
        if not all(
            isinstance(value, (int, float))
            for value in (base_med, cand_med, base_p95, cand_p95)
        ):
            continue
        scenario_id, metric_name = key.split(".", 1)
        delta_median = float(cand_med) - float(base_med)
        delta_p95 = float(cand_p95) - float(base_p95)
        pct_median = _safe_pct(delta_median, float(base_med))
        pct_p95 = _safe_pct(delta_p95, float(base_p95))
        delta = PerfMetricDelta(
            scenario_id=scenario_id,
            metric_name=metric_name,
            unit=base_unit,
            baseline_median=float(base_med),
            candidate_median=float(cand_med),
            delta_median=delta_median,
            pct_median=pct_median,
            baseline_p95=float(base_p95),
            candidate_p95=float(cand_p95),
            delta_p95=delta_p95,
            pct_p95=pct_p95,
        )
        if pct_median is not None and pct_median >= regression_pct_threshold:
            regressed.append(delta)
        elif pct_median is not None and pct_median <= improvement_pct_threshold:
            improved.append(delta)
        else:
            unchanged.append(delta)

    def _sorted_deltas(values: list[PerfMetricDelta]) -> list[PerfMetricDelta]:
        return sorted(
            values,
            key=lambda value: (
                float("-inf") if value.pct_median is None else -value.pct_median
            ),
        )

    return PerfComparisonResult(
        baseline_run_id=str(baseline.get("run_id") or "baseline"),
        candidate_run_id=str(candidate.get("run_id") or "candidate"),
        comparable_metric_count=len(shared_keys),
        regressed_metrics=_sorted_deltas(regressed),
        improved_metrics=_sorted_deltas(improved),
        unchanged_metrics=unchanged,
        missing_in_candidate=sorted(base_keys - cand_keys),
        new_in_candidate=sorted(cand_keys - base_keys),
    )


def write_perf_run_artifact(
    run: PerfRunResult,
    *,
    results_dir: Path | None = None,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> Path:
    """Write benchmark result artifact JSON to local perf-results directory."""
    if results_dir is None:
        results_dir = resolve_perf_results_dir(cwd=cwd, env=env)
    results_dir.mkdir(parents=True, exist_ok=True)
    safe_run_id = "".join(
        ch if ch.isalnum() or ch in "-._" else "_" for ch in run.run_id
    )
    stem = f"{run.created_at.replace(':', '').replace('-', '')}_{safe_run_id}"
    path = results_dir / f"{stem}.json"
    path.write_text(run.to_json() + "\n", encoding="utf-8")
    return path


def load_perf_run_payload(path: Path) -> dict[str, JsonValue]:
    """Load and validate a benchmark result payload from JSON artifact."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("perf artifact root must be a JSON object")
    errors = validate_perf_run_payload(payload)
    if errors:
        joined = "; ".join(errors[:5])
        raise ValueError(f"invalid perf artifact payload: {joined}")
    return payload


def render_perf_comparison_text(
    comparison: PerfComparisonResult, *, max_rows_per_section: int = 10
) -> str:
    """Render human-readable comparison summary."""
    lines = [
        "Perf comparison",
        f"baseline={comparison.baseline_run_id}",
        f"candidate={comparison.candidate_run_id}",
        f"comparable_metrics={comparison.comparable_metric_count}",
        f"regressed={len(comparison.regressed_metrics)} improved={len(comparison.improved_metrics)} unchanged={len(comparison.unchanged_metrics)}",
    ]

    def _append_section(title: str, rows: list[PerfMetricDelta]) -> None:
        lines.append(f"{title}:")
        if not rows:
            lines.append("  none")
            return
        for row in rows[:max_rows_per_section]:
            pct = "n/a" if row.pct_median is None else f"{row.pct_median:+.1f}%"
            lines.append(
                "  "
                f"{row.scenario_id}.{row.metric_name} "
                f"median {row.baseline_median:.3f}->{row.candidate_median:.3f} {row.unit} "
                f"({pct})"
            )

    _append_section("Regressions", comparison.regressed_metrics)
    _append_section("Improvements", comparison.improved_metrics)
    if comparison.missing_in_candidate:
        lines.append("Missing metrics in candidate:")
        for key in comparison.missing_in_candidate[:max_rows_per_section]:
            lines.append(f"  {key}")
    if comparison.new_in_candidate:
        lines.append("New metrics in candidate:")
        for key in comparison.new_in_candidate[:max_rows_per_section]:
            lines.append(f"  {key}")
    return "\n".join(lines)


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
