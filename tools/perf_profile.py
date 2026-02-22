"""Run a Python module under cProfile and write local profiling artifacts.

Example:
  .ubuntu-venv/bin/python tools/perf_profile.py \
    --label controls \
    --module pytest -- tests/test_performance_opt_in.py -k controls_latency
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from tz_player.perf_profiling import (
    profile_timestamp_slug,
    render_pstats_summary_text,
    resolve_perf_profile_dir,
    sanitize_profile_label,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--label",
        default="perf-profile",
        help="Artifact label used in output filenames.",
    )
    parser.add_argument(
        "--module",
        default="pytest",
        help="Python module to run under cProfile (default: pytest).",
    )
    parser.add_argument(
        "--sort",
        default="cumulative",
        help="pstats sort key for text summary (default: cumulative).",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=60,
        help="Top N rows to print in text summary (default: 60).",
    )
    parser.add_argument(
        "module_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed to the target module (prefix with --).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    module_args = list(args.module_args)
    if module_args and module_args[0] == "--":
        module_args = module_args[1:]

    profile_dir = resolve_perf_profile_dir()
    profile_dir.mkdir(parents=True, exist_ok=True)
    slug = f"{profile_timestamp_slug()}_{sanitize_profile_label(args.label)}"
    prof_path = profile_dir / f"{slug}.prof"
    txt_path = profile_dir / f"{slug}.txt"

    cmd = [
        sys.executable,
        "-m",
        "cProfile",
        "-o",
        str(prof_path),
        "-m",
        str(args.module),
        *module_args,
    ]
    print(f"Running: {' '.join(cmd)}")
    completed = subprocess.run(cmd, check=False)

    if prof_path.exists():
        summary = render_pstats_summary_text(
            prof_path, sort_key=str(args.sort), top_n=max(1, int(args.top))
        )
        txt_path.write_text(
            (
                "# cProfile external module run\n"
                f"module: {args.module}\n"
                f"label: {args.label}\n"
                f"sort: {args.sort}\n"
                f"top_n: {max(1, int(args.top))}\n\n"
                f"{summary}"
            ),
            encoding="utf-8",
        )
        print(f"Profile artifacts written:\n- {prof_path}\n- {txt_path}")
    else:
        print("No .prof artifact generated.", file=sys.stderr)

    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
