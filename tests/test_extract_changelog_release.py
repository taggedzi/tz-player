from __future__ import annotations

from tools.extract_changelog_release import extract_release_section


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
