"""Compare two perf suite summary artifacts and auto-pair scenario artifacts."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any

from tz_player.perf_benchmarking import (
    compare_perf_run_payloads,
    load_perf_run_payload,
    render_perf_comparison_text,
)


@dataclass(frozen=True)
class SuiteArtifactEntry:
    path: Path
    scenario_key: str
    scenario_ids: tuple[tuple[str, str], ...]
    created_at: str
    run_id: str
    payload: dict[str, Any]


def _analysis_zero_tracks_warning(payload: dict[str, Any]) -> str | None:
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list):
        return None
    affected: list[str] = []
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            continue
        scenario_id = scenario.get("scenario_id")
        counters = scenario.get("counters")
        if not isinstance(counters, dict):
            continue
        analyzed = counters.get("tracks_analyzed")
        requested = counters.get("tracks_requested")
        if (
            isinstance(analyzed, int)
            and isinstance(requested, int)
            and requested > 0
            and analyzed == 0
            and isinstance(scenario_id, str)
            and scenario_id
        ):
            affected.append(scenario_id)
    if not affected:
        return None
    return "zero_tracks_analyzed=" + ",".join(sorted(affected))


def _analysis_backend_summary(payload: dict[str, Any]) -> str:
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list):
        return "n/a"
    backend_counts: dict[str, int] = {}
    beat_backend_counts: dict[str, int] = {}
    waveform_backend_counts: dict[str, int] = {}
    fallback_counts: dict[str, int] = {}
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            continue
        metadata = scenario.get("metadata")
        if isinstance(metadata, dict):
            raw_backend_counts = metadata.get("analysis_backend_counts")
            if isinstance(raw_backend_counts, dict):
                for key, value in raw_backend_counts.items():
                    if isinstance(key, str) and isinstance(value, int):
                        backend_counts[key] = backend_counts.get(key, 0) + value
            raw_beat_backend_counts = metadata.get("beat_backend_counts")
            if isinstance(raw_beat_backend_counts, dict):
                for key, value in raw_beat_backend_counts.items():
                    if isinstance(key, str) and isinstance(value, int):
                        beat_backend_counts[key] = (
                            beat_backend_counts.get(key, 0) + value
                        )
            raw_waveform_backend_counts = metadata.get("waveform_proxy_backend_counts")
            if isinstance(raw_waveform_backend_counts, dict):
                for key, value in raw_waveform_backend_counts.items():
                    if isinstance(key, str) and isinstance(value, int):
                        waveform_backend_counts[key] = (
                            waveform_backend_counts.get(key, 0) + value
                        )
            raw_fallback_counts = metadata.get("analysis_fallback_reason_counts")
            if isinstance(raw_fallback_counts, dict):
                for key, value in raw_fallback_counts.items():
                    if isinstance(key, str) and isinstance(value, int):
                        fallback_counts[key] = fallback_counts.get(key, 0) + value
    if (
        not backend_counts
        and not beat_backend_counts
        and not waveform_backend_counts
        and not fallback_counts
    ):
        return "n/a"
    parts: list[str] = []
    if backend_counts:
        parts.append(
            "backends="
            + ",".join(f"{key}:{backend_counts[key]}" for key in sorted(backend_counts))
        )
    if beat_backend_counts:
        parts.append(
            "beat="
            + ",".join(
                f"{key}:{beat_backend_counts[key]}" for key in sorted(beat_backend_counts)
            )
        )
    if waveform_backend_counts:
        parts.append(
            "waveform="
            + ",".join(
                f"{key}:{waveform_backend_counts[key]}"
                for key in sorted(waveform_backend_counts)
            )
        )
    if fallback_counts:
        parts.append(
            "fallbacks="
            + ",".join(
                f"{key}:{fallback_counts[key]}" for key in sorted(fallback_counts)
            )
        )
    return " ".join(parts)


def _native_helper_summary(payload: dict[str, Any]) -> str | None:
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list):
        return None
    versions: set[str] = set()
    helper_cmds: set[str] = set()
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            continue
        metadata = scenario.get("metadata")
        if not isinstance(metadata, dict):
            continue
        tracks = metadata.get("tracks")
        if isinstance(tracks, list):
            for track in tracks:
                if isinstance(track, dict):
                    version = track.get("native_helper_version")
                    if isinstance(version, str) and version:
                        versions.add(version)
        helper_cmd = metadata.get("native_helper_cmd")
        if isinstance(helper_cmd, str) and helper_cmd:
            helper_cmds.add(helper_cmd)
    parts: list[str] = []
    if versions:
        parts.append("versions=" + ",".join(sorted(versions)))
    if helper_cmds:
        parts.append("cmd=" + " | ".join(sorted(helper_cmds)))
    return " ".join(parts) if parts else None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline_suite", type=Path, help="Baseline suite summary JSON")
    parser.add_argument(
        "candidate_suite", type=Path, help="Candidate suite summary JSON"
    )
    parser.add_argument(
        "--regression-pct",
        type=float,
        default=5.0,
        help="Percent increase threshold treated as regression (default: 5.0).",
    )
    parser.add_argument(
        "--improvement-pct",
        type=float,
        default=-5.0,
        help="Percent decrease threshold treated as improvement (default: -5.0).",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=8,
        help="Max rows per comparison section (default: 8).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if pairing mismatches exist.",
    )
    return parser.parse_args()


def _load_suite_summary(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"suite summary must be an object: {path}")
    if payload.get("schema") != "tz_player.perf_run_suite_summary.v1":
        raise ValueError(f"unsupported suite summary schema in {path}")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError(f"suite summary missing artifacts list: {path}")
    return payload


def _resolve_artifact_path(raw_path: str) -> Path:
    """Resolve suite artifact path, handling cross-platform Windows path strings."""
    path = Path(raw_path).expanduser()
    if path.exists():
        return path.resolve()
    if ":" in raw_path and "\\" in raw_path:
        try:
            win = PureWindowsPath(raw_path)
            anchor = win.anchor.rstrip("\\/")
            if len(anchor) >= 2 and anchor[1] == ":":
                drive = anchor[0].lower()
                tail_parts = [part for part in win.parts[1:] if part not in {"\\", "/"}]
                wsl_path = Path("/mnt") / drive
                for part in tail_parts:
                    wsl_path /= part
                if wsl_path.exists():
                    return wsl_path.resolve()
        except Exception:
            pass
    return path.resolve()


def _scenario_signature(
    run_payload: dict[str, Any],
) -> tuple[str, tuple[tuple[str, str], ...]]:
    scenarios = run_payload.get("scenarios")
    if not isinstance(scenarios, list):
        return ("unknown", ())
    scenario_pairs: list[tuple[str, str]] = []
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            continue
        sid = scenario.get("scenario_id")
        category = scenario.get("category")
        if isinstance(sid, str) and sid:
            cat = category if isinstance(category, str) and category else "unknown"
            scenario_pairs.append((cat, sid))
    pairs_tuple = tuple(sorted(scenario_pairs))
    if not pairs_tuple:
        return ("unknown", ())
    return (
        "+".join(f"{cat}:{sid}" for cat, sid in pairs_tuple),
        pairs_tuple,
    )


def _load_suite_artifacts(summary: dict[str, Any]) -> list[SuiteArtifactEntry]:
    entries: list[SuiteArtifactEntry] = []
    for raw_path in summary.get("artifacts", []):
        if not isinstance(raw_path, str):
            continue
        path = _resolve_artifact_path(raw_path)
        payload = load_perf_run_payload(path)
        scenario_key, scenario_ids = _scenario_signature(payload)
        entries.append(
            SuiteArtifactEntry(
                path=path,
                scenario_key=scenario_key,
                scenario_ids=scenario_ids,
                created_at=str(payload.get("created_at") or ""),
                run_id=str(payload.get("run_id") or path.stem),
                payload=payload,
            )
        )
    entries.sort(key=lambda e: (e.scenario_key, e.created_at, e.run_id))
    return entries


def _group_by_scenario_key(
    entries: list[SuiteArtifactEntry],
) -> dict[str, list[SuiteArtifactEntry]]:
    grouped: dict[str, list[SuiteArtifactEntry]] = {}
    for entry in entries:
        grouped.setdefault(entry.scenario_key, []).append(entry)
    return grouped


def main() -> int:
    args = _parse_args()
    baseline_summary = _load_suite_summary(args.baseline_suite.resolve())
    candidate_summary = _load_suite_summary(args.candidate_suite.resolve())

    baseline_entries = _load_suite_artifacts(baseline_summary)
    candidate_entries = _load_suite_artifacts(candidate_summary)
    baseline_groups = _group_by_scenario_key(baseline_entries)
    candidate_groups = _group_by_scenario_key(candidate_entries)

    all_keys = sorted(set(baseline_groups) | set(candidate_groups))
    pair_mismatches: list[str] = []
    compared_pairs = 0
    total_regressions = 0
    total_improvements = 0

    print("Perf suite comparison")
    print(f"baseline_suite={args.baseline_suite.resolve()}")
    print(f"candidate_suite={args.candidate_suite.resolve()}")
    print(f"baseline_run_id={baseline_summary.get('run_id')}")
    print(f"candidate_run_id={candidate_summary.get('run_id')}")
    print(f"baseline_status={baseline_summary.get('status')}")
    print(f"candidate_status={candidate_summary.get('status')}")

    for key in all_keys:
        base_list = baseline_groups.get(key, [])
        cand_list = candidate_groups.get(key, [])
        if len(base_list) != len(cand_list):
            pair_mismatches.append(
                f"{key}: baseline_count={len(base_list)} candidate_count={len(cand_list)}"
            )
        pair_count = min(len(base_list), len(cand_list))
        if pair_count <= 0:
            continue

        print(f"\n=== Scenario Group: {key} (pairs={pair_count}) ===")
        for idx in range(pair_count):
            base_entry = base_list[idx]
            cand_entry = cand_list[idx]
            compared_pairs += 1
            comparison = compare_perf_run_payloads(
                base_entry.payload,
                cand_entry.payload,
                regression_pct_threshold=float(args.regression_pct),
                improvement_pct_threshold=float(args.improvement_pct),
            )
            total_regressions += len(comparison.regressed_metrics)
            total_improvements += len(comparison.improved_metrics)
            print(
                f"\n--- Pair {idx + 1}: baseline={base_entry.path.name} "
                f"candidate={cand_entry.path.name} ---"
            )
            print(
                "baseline_backend_meta="
                + _analysis_backend_summary(base_entry.payload)
            )
            print(
                "candidate_backend_meta="
                + _analysis_backend_summary(cand_entry.payload)
            )
            base_helper = _native_helper_summary(base_entry.payload)
            cand_helper = _native_helper_summary(cand_entry.payload)
            if base_helper is not None:
                print(f"baseline_helper_meta={base_helper}")
            if cand_helper is not None:
                print(f"candidate_helper_meta={cand_helper}")
            base_warning = _analysis_zero_tracks_warning(base_entry.payload)
            cand_warning = _analysis_zero_tracks_warning(cand_entry.payload)
            if base_warning is not None:
                print(f"baseline_warning={base_warning}")
            if cand_warning is not None:
                print(f"candidate_warning={cand_warning}")
            print(
                render_perf_comparison_text(
                    comparison, max_rows_per_section=max(1, int(args.max_rows))
                )
            )

    print("\nSuite comparison summary")
    print(f"compared_pairs={compared_pairs}")
    print(f"total_regressions={total_regressions}")
    print(f"total_improvements={total_improvements}")
    if pair_mismatches:
        print("pair_mismatches:")
        for item in pair_mismatches:
            print(f"  {item}")

    if args.strict and pair_mismatches:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
