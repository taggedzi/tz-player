"""One-command release trigger that dispatches and optionally watches Release Cut."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
import time

POLL_SECONDS = 2
POLL_TIMEOUT_SECONDS = 90


def _log(message: str) -> None:
    print(f"[release] {message}")


def _run(cmd: list[str], *, capture: bool = False) -> str:
    result = subprocess.run(cmd, check=True, text=True, capture_output=capture)
    return result.stdout.strip() if capture else ""


def _require_command(cmd: str) -> None:
    if shutil.which(cmd) is None:
        raise RuntimeError(f"Missing required command: {cmd}")


def _parse_version(raw: str) -> str:
    version = raw.strip()
    if version.startswith(("v", "V")):
        version = version[1:]
    if not version:
        raise RuntimeError("Version cannot be empty.")
    return version


def _is_prerelease(version: str) -> bool:
    lowered = version.lower()
    return any(marker in lowered for marker in ("a", "b", "rc", "dev", "alpha", "beta"))


def _workflow_run_name(version: str) -> str:
    return f"Release Cut v{version}"


def _list_release_cut_runs() -> list[dict[str, object]]:
    raw = _run(
        [
            "gh",
            "run",
            "list",
            "--workflow",
            "Release Cut",
            "--event",
            "workflow_dispatch",
            "--limit",
            "30",
            "--json",
            "databaseId,displayTitle,createdAt,status,conclusion",
        ],
        capture=True,
    )
    return json.loads(raw)


def _select_run_id(
    *, version: str, runs: list[dict[str, object]], started_at: dt.datetime
) -> int | None:
    """Pick the most likely run ID for a freshly dispatched release workflow.

    GitHub run timestamps can be a little behind local wall clock, so allow
    modest skew before falling back to the newest matching run title.
    """
    title = _workflow_run_name(version)
    skew_tolerance = dt.timedelta(minutes=5)
    matching: list[tuple[int, dt.datetime]] = []
    for run in runs:
        if str(run.get("displayTitle", "")) != title:
            continue
        run_id = run.get("databaseId")
        if not isinstance(run_id, int):
            continue
        created_at_raw = str(run.get("createdAt", "")).replace("Z", "+00:00")
        try:
            created_at = dt.datetime.fromisoformat(created_at_raw)
        except ValueError:
            created_at = dt.datetime.fromtimestamp(0, tz=dt.timezone.utc)
        matching.append((run_id, created_at))

    if not matching:
        return None

    fresh = [
        (run_id, created_at)
        for run_id, created_at in matching
        if created_at >= started_at - skew_tolerance
    ]
    if fresh:
        return max(fresh, key=lambda item: item[1])[0]
    return max(matching, key=lambda item: item[1])[0]


def _find_dispatched_run_id(*, version: str, started_at: dt.datetime) -> int:
    deadline = time.time() + POLL_TIMEOUT_SECONDS
    while time.time() < deadline:
        run_id = _select_run_id(
            version=version, runs=_list_release_cut_runs(), started_at=started_at
        )
        if run_id is not None:
            return run_id
        time.sleep(POLL_SECONDS)

    raise RuntimeError(
        "Could not locate dispatched Release Cut run. Check manually with: "
        "gh run list --workflow 'Release Cut' --limit 10"
    )


def run_release(
    raw_version: str,
    *,
    prerelease: bool | None,
    sign_artifacts: bool,
    watch: bool,
) -> None:
    version = _parse_version(raw_version)
    tag = f"v{version}"

    _require_command("gh")
    try:
        _run(["gh", "auth", "status"])
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "GitHub CLI is not authenticated. Run: gh auth login"
        ) from exc

    prerelease_value = prerelease if prerelease is not None else _is_prerelease(version)
    prerelease_flag = str(prerelease_value).lower()
    sign_flag = str(sign_artifacts).lower()

    _log(f"Dispatching Release Cut workflow for {tag}")
    started_at = dt.datetime.now(dt.timezone.utc)
    _run(
        [
            "gh",
            "workflow",
            "run",
            "Release Cut",
            "--ref",
            "main",
            "--field",
            f"version={version}",
            "--field",
            f"prerelease={prerelease_flag}",
            "--field",
            f"sign_artifacts={sign_flag}",
        ]
    )

    if not watch:
        _log("Workflow dispatched.")
        _log("Monitor with: gh run list --workflow 'Release Cut' --limit 10")
        _log(f"Verify release when complete: gh release view {tag}")
        return

    run_id = _find_dispatched_run_id(version=version, started_at=started_at)
    _log(f"Watching Release Cut run {run_id}")
    _run(["gh", "run", "watch", str(run_id), "--exit-status"])

    _log("Release Cut workflow completed successfully.")
    _log(f"Release should now be available at tag {tag}.")
    _log(
        f"Inspect release assets: gh release view {tag} --json name,url,tagName,isPrerelease,assets"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="Release version, e.g. 1.2.3 or v1.2.3")
    parser.add_argument(
        "--prerelease",
        action="store_true",
        default=None,
        help="Force prerelease=true (defaults to auto-detect from version string).",
    )
    parser.add_argument(
        "--stable",
        action="store_true",
        help="Force prerelease=false.",
    )
    parser.add_argument(
        "--sign-artifacts",
        action="store_true",
        help="Enable GPG signing in CI (requires release signing secrets).",
    )
    parser.add_argument(
        "--no-watch",
        action="store_true",
        help="Dispatch and exit without streaming workflow progress.",
    )
    args = parser.parse_args()

    if args.prerelease and args.stable:
        print(
            "[release] ERROR: --prerelease and --stable are mutually exclusive.",
            file=sys.stderr,
        )
        return 2

    prerelease: bool | None
    if args.prerelease:
        prerelease = True
    elif args.stable:
        prerelease = False
    else:
        prerelease = None

    try:
        run_release(
            args.version,
            prerelease=prerelease,
            sign_artifacts=args.sign_artifacts,
            watch=not args.no_watch,
        )
    except (RuntimeError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"[release] ERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
