"""Compare two opt-in performance benchmark JSON artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path

from tz_player.perf_benchmarking import (
    compare_perf_run_payloads,
    load_perf_run_payload,
    render_perf_comparison_text,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "baseline", type=Path, help="Path to baseline perf JSON artifact"
    )
    parser.add_argument(
        "candidate", type=Path, help="Path to candidate perf JSON artifact"
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
        default=10,
        help="Max rows per section in text output (default: 10).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    baseline = load_perf_run_payload(args.baseline.resolve())
    candidate = load_perf_run_payload(args.candidate.resolve())
    comparison = compare_perf_run_payloads(
        baseline,
        candidate,
        regression_pct_threshold=float(args.regression_pct),
        improvement_pct_threshold=float(args.improvement_pct),
    )
    print(
        render_perf_comparison_text(
            comparison, max_rows_per_section=max(1, args.max_rows)
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
