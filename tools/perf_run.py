"""Run opt-in performance benchmark scenarios and persist artifacts locally."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

from tz_player.perf_benchmarking import resolve_perf_results_dir

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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        action="append",
        choices=sorted(SCENARIO_TESTS),
        help="Scenario to run (repeatable). Default: all supported scenarios.",
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
        default=Path(".ubuntu-venv/bin/python"),
        help="Python executable used to run pytest (default: .ubuntu-venv/bin/python).",
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
    return parser.parse_args()


def _list_artifacts(results_dir: Path) -> set[Path]:
    if not results_dir.exists():
        return set()
    return {path.resolve() for path in results_dir.glob("*.json") if path.is_file()}


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
    completed = subprocess.run(cmd, env=env, check=False)
    return int(completed.returncode)


def main() -> int:
    args = _parse_args()

    if args.list_scenarios:
        for name, test_name in sorted(SCENARIO_TESTS.items()):
            print(f"{name}: {test_name}")
        return 0

    selected = args.scenario or list(SCENARIO_TESTS)
    repeat = max(1, int(args.repeat))
    python_path = args.pytest_path.resolve()
    extra_pytest_args = list(args.pytest_args or [])

    env = dict(os.environ)
    env["TZ_PLAYER_RUN_PERF"] = "1"
    if args.media_dir is not None:
        env["TZ_PLAYER_PERF_MEDIA_DIR"] = str(args.media_dir.resolve())
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
    print(f"selected_scenarios={selected}")
    print(f"repeat={repeat}")

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

    if failures:
        print("failures:")
        for scenario, run_index, code in failures:
            print(f"  scenario={scenario} run={run_index} exit_code={code}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
