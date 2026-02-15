from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def test_release_prepare_updates_version_and_changelog(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    src = repo / "src" / "tz_player"
    src.mkdir(parents=True)

    (src / "version.py").write_text(
        '"""Project version source of truth."""\n\n__version__ = "0.1.0"\n',
        encoding="utf-8",
    )
    (repo / "CHANGELOG.md").write_text(
        "# Changelog\n\n"
        "## [Unreleased]\n\n"
        "### Added\n\n"
        "- Existing unreleased note.\n\n"
        "### Changed\n\n"
        "- None.\n\n"
        "### Fixed\n\n"
        "- None.\n\n",
        encoding="utf-8",
    )

    _run(["git", "init"], cwd=repo)
    _run(["git", "config", "user.name", "Test"], cwd=repo)
    _run(["git", "config", "user.email", "test@example.com"], cwd=repo)
    _run(["git", "add", "."], cwd=repo)
    _run(["git", "commit", "-m", "chore: baseline"], cwd=repo)
    _run(["git", "tag", "v0.1.0"], cwd=repo)

    (repo / "dummy.txt").write_text("change\n", encoding="utf-8")
    _run(["git", "add", "dummy.txt"], cwd=repo)
    _run(["git", "commit", "-m", "feat: improve startup"], cwd=repo)

    script = Path(__file__).resolve().parents[1] / "tools" / "release_prepare.py"
    notes_file = repo / "RELEASE_NOTES.md"
    _run(
        [
            sys.executable,
            str(script),
            "--version",
            "0.2.0",
            "--date",
            "2026-02-15",
            "--notes-file",
            str(notes_file),
            "--repo-root",
            str(repo),
        ],
        cwd=repo,
    )

    version_text = (src / "version.py").read_text(encoding="utf-8")
    assert '__version__ = "0.2.0"' in version_text

    changelog = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## [Unreleased]" in changelog
    assert "## [0.2.0] - 2026-02-15" in changelog
    assert "- Existing unreleased note." in changelog
    assert "- Improve startup" in changelog
    assert changelog.count("- None.") >= 3

    notes = notes_file.read_text(encoding="utf-8")
    assert "## [0.2.0] - 2026-02-15" in notes
    assert "- Improve startup" in notes
