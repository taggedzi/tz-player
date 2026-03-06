from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_release_module():
    repo_root = Path(__file__).resolve().parents[1]
    release_path = repo_root / "tools" / "release.py"
    spec = importlib.util.spec_from_file_location("tz_release", release_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load release module from {release_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release = _load_release_module()


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
