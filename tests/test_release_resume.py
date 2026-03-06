from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


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


def test_parse_version_accepts_prefixed_tag() -> None:
    assert release._parse_version("v1.2.3") == "1.2.3"


def test_parse_version_rejects_empty_input() -> None:
    with pytest.raises(RuntimeError, match="Version cannot be empty"):
        release._parse_version("v")


def test_workflow_run_name_uses_normalized_tag_prefix() -> None:
    assert release._workflow_run_name("1.2.3") == "Release Cut v1.2.3"


def test_prerelease_detection() -> None:
    assert release._is_prerelease("1.2.3rc1") is True
    assert release._is_prerelease("1.2.3") is False
