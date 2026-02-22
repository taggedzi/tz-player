"""Optional deep-profile helpers for local perf investigations.

These utilities are intentionally separate from the standard opt-in benchmark
suite so profiling overhead does not distort regular benchmark comparisons.
"""

from __future__ import annotations

import cProfile
import io
import os
import pstats
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

PERF_PROFILE_DIR_ENV = "TZ_PLAYER_PERF_PROFILE_DIR"
DEFAULT_LOCAL_PERF_PROFILE_DIR = Path(".local/perf_profiles")


def resolve_perf_profile_dir(
    *, cwd: Path | None = None, env: dict[str, str] | None = None
) -> Path:
    """Resolve local profile artifact directory path."""
    if env is None:
        env = os.environ
    if cwd is None:
        cwd = Path.cwd()
    explicit = env.get(PERF_PROFILE_DIR_ENV)
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_absolute():
            path = (cwd / path).resolve()
        return path
    return (cwd / DEFAULT_LOCAL_PERF_PROFILE_DIR).resolve()


def profile_timestamp_slug() -> str:
    """Return a filesystem-friendly UTC timestamp slug."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sanitize_profile_label(label: str) -> str:
    """Sanitize label for filenames."""
    sanitized = "".join(
        ch if ch.isalnum() or ch in "-._" else "_" for ch in label.strip()
    )
    return sanitized or "profile"


@dataclass(frozen=True)
class CProfileArtifact:
    """Result of a cProfile run and exported summaries."""

    label: str
    elapsed_s: float
    prof_path: Path
    summary_path: Path
    sort_key: str
    top_n: int


def render_pstats_summary_text(
    prof_path: Path, *, sort_key: str = "cumulative", top_n: int = 50
) -> str:
    """Render a text summary from a `.prof` artifact using `pstats`."""
    stream = io.StringIO()
    stats = pstats.Stats(str(prof_path), stream=stream)
    stats.sort_stats(sort_key)
    stats.print_stats(max(1, int(top_n)))
    return stream.getvalue()


def run_cprofile_callable(
    func,
    /,
    *args,
    label: str,
    profile_dir: Path | None = None,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    sort_key: str = "cumulative",
    top_n: int = 50,
    **kwargs,
) -> tuple[object, CProfileArtifact]:
    """Run a callable under cProfile and write `.prof` + text summary artifacts."""
    if profile_dir is None:
        profile_dir = resolve_perf_profile_dir(cwd=cwd, env=env)
    profile_dir.mkdir(parents=True, exist_ok=True)

    slug = f"{profile_timestamp_slug()}_{sanitize_profile_label(label)}"
    prof_path = profile_dir / f"{slug}.prof"
    summary_path = profile_dir / f"{slug}.txt"

    profiler = cProfile.Profile()
    start = time.perf_counter()
    result = profiler.runcall(func, *args, **kwargs)
    elapsed = time.perf_counter() - start
    profiler.dump_stats(str(prof_path))

    summary_text = render_pstats_summary_text(
        prof_path, sort_key=sort_key, top_n=max(1, int(top_n))
    )
    summary_header = (
        f"# cProfile summary\n"
        f"label: {label}\n"
        f"elapsed_s: {elapsed:.6f}\n"
        f"sort: {sort_key}\n"
        f"top_n: {int(top_n)}\n\n"
    )
    summary_path.write_text(summary_header + summary_text, encoding="utf-8")

    artifact = CProfileArtifact(
        label=label,
        elapsed_s=elapsed,
        prof_path=prof_path,
        summary_path=summary_path,
        sort_key=sort_key,
        top_n=max(1, int(top_n)),
    )
    return result, artifact
