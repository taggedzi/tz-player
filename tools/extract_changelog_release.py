"""Extract a specific release section from CHANGELOG.md."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def extract_release_section(*, changelog_text: str, version: str) -> str:
    """Extract one release heading block from changelog text by version."""
    version = version.strip()
    if version.startswith(("v", "V")):
        version = version[1:]
    if not version.strip():
        raise ValueError("Version must not be empty.")
    pattern = re.compile(
        rf"^## \[{re.escape(version)}\].*?(?=^## \[|\Z)", re.MULTILINE | re.DOTALL
    )
    match = pattern.search(changelog_text)
    if not match:
        raise ValueError(f"Version section [{version}] not found in changelog.")
    return match.group(0).rstrip() + "\n"


def main() -> int:
    """CLI entrypoint for writing extracted release section to output file."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="Version to extract.")
    parser.add_argument(
        "--changelog",
        type=Path,
        default=Path("CHANGELOG.md"),
        help="Path to changelog.",
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="Output file for release notes."
    )
    args = parser.parse_args()

    changelog_text = args.changelog.read_text(encoding="utf-8")
    release_notes = extract_release_section(
        changelog_text=changelog_text, version=args.version
    )
    args.output.write_text(release_notes, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
