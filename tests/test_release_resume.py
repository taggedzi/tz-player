from __future__ import annotations

import datetime as dt
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


def test_select_run_id_tolerates_small_clock_skew() -> None:
    started_at = dt.datetime(2026, 3, 6, 18, 0, tzinfo=dt.timezone.utc)
    runs = [
        {
            "databaseId": 1001,
            "displayTitle": "Release Cut v1.1.2",
            "createdAt": "2026-03-06T17:58:30Z",
        }
    ]
    assert (
        release._select_run_id(version="1.1.2", runs=runs, started_at=started_at)
        == 1001
    )


def test_select_run_id_prefers_newest_matching_title() -> None:
    started_at = dt.datetime(2026, 3, 6, 18, 0, tzinfo=dt.timezone.utc)
    runs = [
        {
            "databaseId": 1000,
            "displayTitle": "Release Cut v1.1.2",
            "createdAt": "2026-03-05T12:00:00Z",
        },
        {
            "databaseId": 1002,
            "displayTitle": "Release Cut v1.1.2",
            "createdAt": "2026-03-06T18:01:00Z",
        },
        {
            "databaseId": 1003,
            "displayTitle": "Release Cut v1.1.1",
            "createdAt": "2026-03-06T18:02:00Z",
        },
    ]
    assert (
        release._select_run_id(version="1.1.2", runs=runs, started_at=started_at)
        == 1002
    )
