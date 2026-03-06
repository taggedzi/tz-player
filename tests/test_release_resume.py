from tools import release


def test_recovery_hints_when_tag_exists() -> None:
    lines = release._recovery_hints(
        version="1.2.3",
        tag="v1.2.3",
        branch="release/v1.2.3",
        tag_exists=True,
        branch_exists=True,
    )
    assert any("Tag v1.2.3 already exists" in line for line in lines)
    assert any("force_rebuild=true" in line for line in lines)


def test_recovery_hints_when_branch_exists() -> None:
    lines = release._recovery_hints(
        version="1.2.3",
        tag="v1.2.3",
        branch="release/v1.2.3",
        tag_exists=False,
        branch_exists=True,
    )
    assert any("Release branch release/v1.2.3 already exists" in line for line in lines)
    assert any("--resume" in line for line in lines)


def test_recovery_hints_default() -> None:
    lines = release._recovery_hints(
        version="1.2.3",
        tag="v1.2.3",
        branch="release/v1.2.3",
        tag_exists=False,
        branch_exists=False,
    )
    assert lines[-1] == "Fix the failure and re-run the same release command."
