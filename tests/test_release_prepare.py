"""Tests for `tools/release_prepare.py` end-to-end release file updates."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


def _run(cmd: list[str], cwd: Path) -> None:
    """Run subprocess command in repo fixture and fail loudly on non-zero exit."""
    subprocess.run(cmd, cwd=cwd, check=True)


def test_release_prepare_updates_version_and_changelog(tmp_path: Path) -> None:
    import importlib.util
    from unittest.mock import patch

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

    script_path = Path(__file__).resolve().parents[1] / "tools" / "release_prepare.py"
    spec = importlib.util.spec_from_file_location("release_prepare", script_path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    def _fake_run_git(args: list[str]) -> str:
        if args[0] == "describe":
            return "v0.1.0"
        if args[0] == "log":
            return "feat: improve startup"
        return ""

    notes_file = repo / "RELEASE_NOTES.md"
    with patch.object(module, "_run_git", side_effect=_fake_run_git):
        module.prepare_release(
            repo_root=repo,
            version="0.2.0",
            release_date="2026-02-15",
            notes_file=notes_file,
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


def test_release_prepare_accepts_v_prefixed_version(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    src = repo / "src" / "tz_player"
    src.mkdir(parents=True)

    (src / "version.py").write_text('__version__ = "0.1.0"\n', encoding="utf-8")
    (repo / "CHANGELOG.md").write_text(
        "# Changelog\n\n"
        "## [Unreleased]\n\n"
        "### Added\n\n"
        "- None.\n\n"
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

    script = Path(__file__).resolve().parents[1] / "tools" / "release_prepare.py"
    _run(
        [
            sys.executable,
            str(script),
            "--version",
            "v0.2.0",
            "--date",
            "2026-02-15",
            "--repo-root",
            str(repo),
        ],
        cwd=repo,
    )

    version_text = (src / "version.py").read_text(encoding="utf-8")
    assert '__version__ = "0.2.0"' in version_text


def test_release_prepare_rejects_invalid_date(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    src = repo / "src" / "tz_player"
    src.mkdir(parents=True)

    (src / "version.py").write_text('__version__ = "0.1.0"\n', encoding="utf-8")
    (repo / "CHANGELOG.md").write_text(
        "# Changelog\n\n"
        "## [Unreleased]\n\n"
        "### Added\n\n"
        "- None.\n\n"
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

    script = Path(__file__).resolve().parents[1] / "tools" / "release_prepare.py"
    with pytest.raises(subprocess.CalledProcessError):
        _run(
            [
                sys.executable,
                str(script),
                "--version",
                "0.2.0",
                "--date",
                "2026-02-30",
                "--repo-root",
                str(repo),
            ],
            cwd=repo,
        )
