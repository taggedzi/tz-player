"""One-command release orchestrator."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time


def _log(message: str) -> None:
    """Emit release-script progress line with stable prefix."""
    print(f"[release] {message}")


def _run(cmd: list[str], *, capture: bool = False) -> str:
    """Run subprocess command and optionally return stdout text."""
    result = subprocess.run(
        cmd,
        check=True,
        text=True,
        capture_output=capture,
    )
    return result.stdout.strip() if capture else ""


def _require_command(cmd: str) -> None:
    """Raise if required external command is unavailable on PATH."""
    if shutil.which(cmd) is None:
        raise RuntimeError(f"Missing required command: {cmd}")


def _python_cmd() -> list[str]:
    """Return interpreter command used for child Python invocations."""
    return [sys.executable]


def _release_prepare(version: str) -> None:
    """Invoke release-prepare helper script for target version."""
    _run([*_python_cmd(), "tools/release_prepare.py", "--version", version])


def _quality_gates() -> None:
    """Run required lint/format/type/test gates before release branch commit."""
    _run([*_python_cmd(), "-m", "ruff", "check", "."])
    _run([*_python_cmd(), "-m", "ruff", "format", "--check", "."])
    _run([*_python_cmd(), "-m", "mypy", "src"])
    _run([*_python_cmd(), "-m", "pytest"])


def _ensure_clean_tree() -> None:
    """Require clean git working tree before release automation proceeds."""
    status = _run(["git", "status", "--porcelain"], capture=True)
    if status:
        raise RuntimeError("Working tree is not clean. Commit or stash changes first.")


def _ref_exists_locally(ref: str) -> bool:
    """Return whether git reference exists in local repository."""
    try:
        _run(["git", "rev-parse", ref], capture=True)
    except subprocess.CalledProcessError:
        return False
    return True


def _ref_exists_remote(*, kind: str, name: str) -> bool:
    """Return whether branch/tag exists on origin remote."""
    out = _run(["git", "ls-remote", f"--{kind}", "origin", name], capture=True)
    return bool(out.strip())


def _parse_version(raw: str) -> str:
    """Normalize input version allowing optional leading `v` prefix."""
    version = raw.strip()
    if version.startswith(("v", "V")):
        version = version[1:]
    if not version:
        raise RuntimeError("Version cannot be empty.")
    return version


def _wait_for_merge(
    pr_url: str, *, timeout_seconds: int = 1800, poll_seconds: int = 5
) -> str:
    """Wait until PR is merged and return merge commit SHA."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        raw = _run(
            [
                "gh",
                "pr",
                "view",
                pr_url,
                "--json",
                "state,mergedAt,mergeCommit",
            ],
            capture=True,
        )
        payload = json.loads(raw)
        state = payload.get("state")
        merged_at = payload.get("mergedAt")
        merge_commit = payload.get("mergeCommit") or {}
        merge_sha = merge_commit.get("oid")

        if merged_at and merge_sha:
            return str(merge_sha)
        if state == "CLOSED" and not merged_at:
            raise RuntimeError(f"PR {pr_url} was closed without being merged.")
        time.sleep(poll_seconds)

    raise RuntimeError(f"Timed out waiting for PR merge: {pr_url}")


def run_release(raw_version: str) -> None:
    """End-to-end release workflow from prep branch to pushed tag."""
    version = _parse_version(raw_version)
    tag = f"v{version}"
    branch = f"release/{tag}"

    _require_command("git")
    _require_command("gh")

    try:
        _run(["gh", "auth", "status"])
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "GitHub CLI is not authenticated. Run: gh auth login"
        ) from exc

    _ensure_clean_tree()

    _log("Fetching latest main")
    _run(["git", "fetch", "origin", "main", "--prune"])
    _run(["git", "switch", "main"])
    _run(["git", "pull", "--ff-only", "origin", "main"])

    if _ref_exists_locally(tag) or _ref_exists_remote(kind="tags", name=tag):
        raise RuntimeError(f"Tag {tag} already exists locally or on origin.")
    if _ref_exists_locally(f"refs/heads/{branch}"):
        raise RuntimeError(f"Local branch {branch} already exists.")
    if _ref_exists_remote(kind="heads", name=branch):
        raise RuntimeError(f"Remote branch {branch} already exists.")

    _log(f"Creating release branch {branch}")
    _run(["git", "switch", "-c", branch])

    _log("Preparing version/changelog")
    _release_prepare(version)

    _log("Running quality gates")
    _quality_gates()

    _run(["git", "add", "src/tz_player/version.py", "CHANGELOG.md"])
    if not _run(["git", "diff", "--cached", "--name-only"], capture=True):
        raise RuntimeError("No release changes detected after preparation.")

    _log("Committing release metadata")
    _run(["git", "commit", "-m", f"release: {tag}"])

    _log("Pushing release branch")
    _run(["git", "push", "-u", "origin", branch])

    _log("Opening pull request")
    pr_url = _run(
        [
            "gh",
            "pr",
            "create",
            "--base",
            "main",
            "--head",
            branch,
            "--title",
            f"release: {tag}",
            "--body",
            f"Automated release prep for {tag}.",
        ],
        capture=True,
    )
    _log(f"PR: {pr_url}")

    _log("Waiting for PR checks to finish")
    _run(["gh", "pr", "checks", pr_url, "--watch", "--fail-fast"])

    _log("Enabling auto-merge for PR")
    _run(["gh", "pr", "merge", pr_url, "--auto", "--squash", "--delete-branch"])

    _log("Waiting for PR merge")
    merge_sha = _wait_for_merge(pr_url)

    _log(f"Refreshing main and creating tag {tag}")
    _run(["git", "fetch", "origin", "main", "--prune"])
    _run(["git", "switch", "main"])
    _run(["git", "pull", "--ff-only", "origin", "main"])
    _run(["git", "tag", "-a", tag, merge_sha, "-m", f"Release {tag}"])

    _log(f"Pushing tag {tag}")
    _run(["git", "push", "origin", tag])

    _log(f"Done. Tag {tag} pushed and GitHub Release workflow should start.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="Release version, e.g. 0.5.2 or v0.5.2")
    args = parser.parse_args()

    try:
        run_release(args.version)
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"[release] ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
