"""Prepare a manual release by updating version/changelog and notes."""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
from collections.abc import Iterable
from pathlib import Path

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?(?:\.post\d+)?(?:\.dev\d+)?$")
CHANGELOG_UNRELEASED_RE = re.compile(
    r"^## \[Unreleased\]\n(?P<body>.*?)(?=^## \[|\Z)", re.MULTILINE | re.DOTALL
)
VERSION_LINE_RE = re.compile(r'^__version__ = "[^"]+"$', re.MULTILINE)
HEADING_RE = re.compile(r"^### (Added|Changed|Fixed)\s*$", re.MULTILINE)


def _run_git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def _latest_tag() -> str | None:
    try:
        tag = _run_git(["describe", "--tags", "--abbrev=0", "--match", "v*"])
    except subprocess.CalledProcessError:
        return None
    return tag or None


def _normalize_commit_subject(subject: str) -> str:
    text = subject.strip()
    text = re.sub(
        r"^(feat|fix|docs|chore|refactor|test|perf|build|ci)(\([^)]+\))?!?:\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return text[:1].upper() + text[1:] if text else text


def _categorize_commit(subject: str) -> str:
    lower = subject.lower().strip()
    if lower.startswith(("feat", "add")):
        return "Added"
    if lower.startswith(("fix", "bug", "hotfix")):
        return "Fixed"
    return "Changed"


def _commit_buckets() -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {"Added": [], "Changed": [], "Fixed": []}
    last_tag = _latest_tag()
    range_expr = "HEAD" if last_tag is None else f"{last_tag}..HEAD"
    output = _run_git(["log", "--no-merges", "--pretty=%s", range_expr])
    subjects = [line.strip() for line in output.splitlines() if line.strip()]
    for subject in subjects:
        bucket = _categorize_commit(subject)
        buckets[bucket].append(_normalize_commit_subject(subject))
    return buckets


def _parse_unreleased_buckets(unreleased_body: str) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {"Added": [], "Changed": [], "Fixed": []}
    headings = list(HEADING_RE.finditer(unreleased_body))
    if not headings:
        return buckets
    for idx, heading in enumerate(headings):
        category = heading.group(1)
        start = heading.end()
        end = (
            headings[idx + 1].start()
            if idx + 1 < len(headings)
            else len(unreleased_body)
        )
        block = unreleased_body[start:end]
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped.startswith("- "):
                continue
            item = stripped[2:].strip()
            if not item or item.lower() == "none.":
                continue
            buckets[category].append(item)
    return buckets


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = value.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _render_section(version: str, date_str: str, buckets: dict[str, list[str]]) -> str:
    lines = [f"## [{version}] - {date_str}", ""]
    for category in ("Added", "Changed", "Fixed"):
        lines.append(f"### {category}")
        lines.append("")
        if buckets[category]:
            lines.extend([f"- {item}" for item in buckets[category]])
        else:
            lines.append("- None.")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_unreleased_template() -> str:
    return (
        "## [Unreleased]\n\n"
        "### Added\n\n"
        "- None.\n\n"
        "### Changed\n\n"
        "- None.\n\n"
        "### Fixed\n\n"
        "- None.\n\n"
    )


def prepare_release(
    *, repo_root: Path, version: str, release_date: str, notes_file: Path | None
) -> None:
    version = version.strip()
    if version.startswith(("v", "V")):
        version = version[1:]
    if VERSION_RE.fullmatch(version) is None:
        raise ValueError(
            f"Invalid version '{version}'. Expected SemVer-like or PEP 440 (for example 1.2.3 or 1.2.3rc1)."
        )
    try:
        release_date = dt.date.fromisoformat(release_date.strip()).isoformat()
    except ValueError as exc:
        raise ValueError(
            f"Invalid release date '{release_date}'. Expected YYYY-MM-DD."
        ) from exc

    version_file = repo_root / "src" / "tz_player" / "version.py"
    changelog_file = repo_root / "CHANGELOG.md"

    version_text = version_file.read_text(encoding="utf-8")
    updated_version_text, count = VERSION_LINE_RE.subn(
        f'__version__ = "{version}"', version_text, count=1
    )
    if count != 1:
        raise ValueError(f"Could not locate __version__ assignment in {version_file}")
    version_file.write_text(updated_version_text, encoding="utf-8")

    changelog_text = changelog_file.read_text(encoding="utf-8")
    match = CHANGELOG_UNRELEASED_RE.search(changelog_text)
    if not match:
        raise ValueError("CHANGELOG.md is missing the [Unreleased] section.")

    unreleased_buckets = _parse_unreleased_buckets(match.group("body"))
    commit_buckets = _commit_buckets()
    merged_buckets = {
        key: _dedupe([*unreleased_buckets[key], *commit_buckets[key]])
        for key in ("Added", "Changed", "Fixed")
    }

    release_section = _render_section(version, release_date, merged_buckets)
    unreleased_section = _render_unreleased_template()
    replacement = f"{unreleased_section}\n{release_section}"
    updated_changelog = (
        changelog_text[: match.start()] + replacement + changelog_text[match.end() :]
    )
    changelog_file.write_text(updated_changelog, encoding="utf-8")

    if notes_file is not None:
        notes_file.write_text(release_section, encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version", required=True, help="Release version (for example 1.2.3)."
    )
    parser.add_argument(
        "--date",
        default=dt.date.today().isoformat(),
        help="Release date in YYYY-MM-DD format (defaults to today).",
    )
    parser.add_argument(
        "--notes-file",
        type=Path,
        default=None,
        help="Optional markdown output file for release notes.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Optional repository root. Defaults to this script's parent repository.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    repo_root = (
        args.repo_root.resolve()
        if args.repo_root is not None
        else Path(__file__).resolve().parents[1]
    )
    prepare_release(
        repo_root=repo_root,
        version=args.version,
        release_date=args.date,
        notes_file=args.notes_file,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
