"""Tests for changelog release-section extraction utility script."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_extract_release_section():
    """Dynamically load tool module function under test from `tools/`."""
    module_path = (
        Path(__file__).resolve().parents[1] / "tools" / "extract_changelog_release.py"
    )
    spec = importlib.util.spec_from_file_location(
        "extract_changelog_release", module_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module spec from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.extract_release_section


extract_release_section = _load_extract_release_section()


def test_extract_release_section_accepts_prefixed_version() -> None:
    changelog = (
        "# Changelog\n\n"
        "## [Unreleased]\n\n"
        "### Added\n\n"
        "- None.\n\n"
        "## [0.5.1] - 2026-02-15\n\n"
        "### Added\n\n"
        "- Feature A.\n\n"
        "## [0.5.0] - 2026-02-14\n\n"
        "### Fixed\n\n"
        "- Bug B.\n"
    )
    section = extract_release_section(changelog_text=changelog, version="v0.5.1")
    assert section.startswith("## [0.5.1] - 2026-02-15")
    assert "- Feature A." in section
    assert "## [0.5.0]" not in section


def test_extract_release_section_rejects_empty_version() -> None:
    with pytest.raises(ValueError, match="Version must not be empty"):
        extract_release_section(changelog_text="## [0.1.0]\n", version="v")
