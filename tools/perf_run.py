"""Run opt-in performance benchmark scenarios and persist artifacts locally."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from tz_player.perf_benchmarking import (
    build_perf_media_manifest,
    perf_media_skip_reason,
    resolve_perf_media_dir,
    resolve_perf_results_dir,
)

SCENARIO_TESTS: dict[str, str] = {
    "track-switch": "test_player_service_track_switch_and_preload_benchmark_smoke",
    "analysis-cache": "test_real_analysis_cache_cold_warm_benchmark_artifact",
    "controls": "test_controls_latency_jitter_under_background_load_benchmark",
    "visualizer-matrix": "test_advanced_visualizer_matrix_benchmark_artifact",
    "db-query-matrix": "test_large_playlist_db_query_matrix_benchmark_artifact",
    "hidden-hotspot-call-probe": "test_hidden_hotspot_idle_and_control_burst_call_probe_artifact",
    "hidden-hotspot-save-log": "test_hidden_hotspot_state_save_and_logging_overhead_artifact",
    "resource-trend": "test_resource_usage_phase_trend_artifact",
}

SUITE_SCENARIOS: dict[str, list[str]] = {
    "user-feel": [
        "analysis-cache",
        "track-switch",
        "controls",
        "visualizer-matrix",
        "db-query-matrix",
        "hidden-hotspot-call-probe",
        "hidden-hotspot-save-log",
        "resource-trend",
    ],
    "analysis": ["analysis-cache", "track-switch"],
    "visualizers": ["visualizer-matrix"],
    "controls-ui": ["controls", "hidden-hotspot-call-probe", "hidden-hotspot-save-log"],
    "database": ["db-query-matrix"],
    "hidden-hotspot": [
        "hidden-hotspot-call-probe",
        "hidden-hotspot-save-log",
        "resource-trend",
    ],
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        action="append",
        choices=sorted(SCENARIO_TESTS),
        help="Scenario to run (repeatable). Default: all supported scenarios.",
    )
    parser.add_argument(
        "--suite",
        action="append",
        choices=sorted(SUITE_SCENARIOS),
        help="Named scenario suite to run (repeatable).",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Repeat each selected scenario this many times (default: 1).",
    )
    parser.add_argument(
        "--media-dir",
        type=Path,
        help="Override perf media corpus directory (sets TZ_PLAYER_PERF_MEDIA_DIR).",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        help=(
            "Override artifact output directory "
            "(sets TZ_PLAYER_PERF_RESULTS_DIR, default .local/perf_results/)."
        ),
    )
    parser.add_argument(
        "--pytest-path",
        type=Path,
        help=(
            "Python executable used to run pytest "
            "(default: auto-detect current interpreter / local venv)."
        ),
    )
    parser.add_argument(
        "--pytest-args",
        nargs=argparse.REMAINDER,
        help="Extra args passed through to pytest after '--pytest-args'.",
    )
    parser.add_argument(
        "--list-scenarios",
        action="store_true",
        help="List supported scenario names and exit.",
    )
    parser.add_argument(
        "--list-suites",
        action="store_true",
        help="List supported suites and their scenario members, then exit.",
    )
    parser.add_argument(
        "--label",
        help="Optional label included in suite summary artifact filename.",
    )
    return parser.parse_args()


def _list_artifacts(results_dir: Path) -> set[Path]:
    if not results_dir.exists():
        return set()
    return {path.resolve() for path in results_dir.glob("*.json") if path.is_file()}


def _resolve_pytest_python(explicit: Path | None) -> Path:
    """Pick a pytest runner interpreter that is valid on the current platform."""
    if explicit is not None:
        return explicit.resolve()

    candidates = [Path(sys.executable)]
    if os.name == "nt":
        candidates.extend(
            [
                Path(".venv/Scripts/python.exe"),
                Path(".ubuntu-venv/Scripts/python.exe"),
                Path("venv/Scripts/python.exe"),
            ]
        )
    else:
        candidates.extend(
            [
                Path(".ubuntu-venv/bin/python"),
                Path(".venv/bin/python"),
                Path("venv/bin/python"),
            ]
        )

    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            continue
        if resolved.exists() and resolved.is_file():
            return resolved
    return Path(sys.executable).resolve()


def _run_pytest_scenario(
    *,
    python_path: Path,
    test_name: str,
    env: dict[str, str],
    extra_pytest_args: list[str],
) -> int:
    cmd = [
        str(python_path),
        "-m",
        "pytest",
        "tests/test_performance_opt_in.py",
        "-q",
        "-k",
        test_name,
    ]
    cmd.extend(extra_pytest_args)
    try:
        completed = subprocess.run(cmd, env=env, check=False)
    except OSError as exc:
        raise RuntimeError(
            f"Failed to launch pytest runner at {python_path!s}: {exc}. "
            "Try --pytest-path pointing to your active venv interpreter."
        ) from exc
    return int(completed.returncode)


def _expand_selection(
    *,
    scenarios: list[str] | None,
    suites: list[str] | None,
) -> tuple[list[str], list[str]]:
    selected: list[str] = []
    seen: set[str] = set()
    suite_names = list(suites or [])
    if suite_names:
        for suite_name in suite_names:
            for scenario in SUITE_SCENARIOS[suite_name]:
                if scenario not in seen:
                    seen.add(scenario)
                    selected.append(scenario)
    if scenarios:
        for scenario in scenarios:
            if scenario not in seen:
                seen.add(scenario)
                selected.append(scenario)
    if not selected:
        selected = list(SCENARIO_TESTS)
    return selected, suite_names


def _write_suite_summary_artifact(
    *,
    results_dir: Path,
    label: str | None,
    selected_scenarios: list[str],
    selected_suites: list[str],
    repeat: int,
    media_dir: Path | None,
    media_manifest: dict[str, object] | None,
    media_skip_reason: str | None,
    new_artifacts: list[Path],
    failures: list[tuple[str, int, int]],
) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    safe_label = "".join(
        ch if ch.isalnum() or ch in "-._" else "_" for ch in (label or "perf-run")
    )
    run_id = f"suite-{safe_label}-{uuid.uuid4().hex[:8]}"
    timestamp = _utc_now_iso()
    path = results_dir / (
        f"{timestamp.replace(':', '').replace('-', '')}_{safe_label}_suite_summary.json"
    )
    payload = {
        "schema": "tz_player.perf_run_suite_summary.v1",
        "run_id": run_id,
        "created_at": timestamp,
        "selected_suites": selected_suites,
        "selected_scenarios": selected_scenarios,
        "repeat": repeat,
        "media_dir": None if media_dir is None else str(media_dir),
        "media_skip_reason": media_skip_reason,
        "media_manifest": media_manifest,
        "results_dir": str(results_dir),
        "new_artifact_count": len(new_artifacts),
        "artifacts": [str(path) for path in new_artifacts],
        "failures": [
            {"scenario": scenario, "run_index": run_index, "exit_code": code}
            for scenario, run_index, code in failures
        ],
        "status": "pass" if not failures else "fail",
    }
    path.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=True) + "\n")
    return path


def main() -> int:
    args = _parse_args()

    if args.list_scenarios:
        for name, test_name in sorted(SCENARIO_TESTS.items()):
            print(f"{name}: {test_name}")
        return 0
    if args.list_suites:
        for name, scenarios in sorted(SUITE_SCENARIOS.items()):
            print(f"{name}: {', '.join(scenarios)}")
        return 0

    selected, selected_suites = _expand_selection(
        scenarios=args.scenario,
        suites=args.suite,
    )
    repeat = max(1, int(args.repeat))
    python_path = _resolve_pytest_python(args.pytest_path)
    extra_pytest_args = list(args.pytest_args or [])

    env = dict(os.environ)
    env["TZ_PLAYER_RUN_PERF"] = "1"
    if args.media_dir is not None:
        env["TZ_PLAYER_PERF_MEDIA_DIR"] = str(args.media_dir.resolve())
    media_dir = resolve_perf_media_dir(cwd=Path.cwd(), env=env)
    media_reason = perf_media_skip_reason(media_dir)
    media_manifest = (
        None
        if media_reason is not None or media_dir is None
        else build_perf_media_manifest(media_dir, probe_durations=False)
    )
    results_dir = (
        args.results_dir.resolve()
        if args.results_dir is not None
        else resolve_perf_results_dir(cwd=Path.cwd(), env=env)
    )
    env["TZ_PLAYER_PERF_RESULTS_DIR"] = str(results_dir)

    before = _list_artifacts(results_dir)
    failures: list[tuple[str, int, int]] = []

    print(f"results_dir={results_dir}")
    print(f"python={python_path}")
    print(f"selected_suites={selected_suites}")
    print(f"selected_scenarios={selected}")
    print(f"repeat={repeat}")
    if media_dir is not None:
        print(f"media_dir={media_dir}")
    if media_reason is not None:
        print(f"media_status={media_reason}")
    elif media_manifest is not None:
        print(
            "media_manifest="
            f"tracks={media_manifest.get('track_count')} "
            f"bytes={media_manifest.get('total_bytes')}"
        )

    for scenario in selected:
        test_name = SCENARIO_TESTS[scenario]
        for run_index in range(1, repeat + 1):
            print(f"\n==> running {scenario} ({run_index}/{repeat})")
            code = _run_pytest_scenario(
                python_path=python_path,
                test_name=test_name,
                env=env,
                extra_pytest_args=extra_pytest_args,
            )
            if code != 0:
                failures.append((scenario, run_index, code))

    after = _list_artifacts(results_dir)
    new_artifacts = sorted(after - before)

    print("\nPerf run summary")
    print(f"new_artifact_count={len(new_artifacts)}")
    for path in new_artifacts:
        print(f"artifact={path}")

    suite_summary_path = _write_suite_summary_artifact(
        results_dir=results_dir,
        label=args.label,
        selected_scenarios=selected,
        selected_suites=selected_suites,
        repeat=repeat,
        media_dir=media_dir,
        media_manifest=media_manifest,
        media_skip_reason=media_reason,
        new_artifacts=new_artifacts,
        failures=failures,
    )
    print(f"suite_summary={suite_summary_path}")

    if failures:
        print("failures:")
        for scenario, run_index, code in failures:
            print(f"  scenario={scenario} run={run_index} exit_code={code}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
