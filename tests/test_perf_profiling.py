from __future__ import annotations

from pathlib import Path

from tz_player.perf_profiling import (
    PERF_PROFILE_DIR_ENV,
    render_pstats_summary_text,
    resolve_perf_profile_dir,
    run_cprofile_callable,
    sanitize_profile_label,
)


def test_resolve_perf_profile_dir_defaults_and_env_override(tmp_path: Path) -> None:
    default_dir = resolve_perf_profile_dir(cwd=tmp_path, env={})
    assert default_dir == (tmp_path / ".local" / "perf_profiles").resolve()

    custom_dir = resolve_perf_profile_dir(
        cwd=tmp_path, env={PERF_PROFILE_DIR_ENV: "profiles_out"}
    )
    assert custom_dir == (tmp_path / "profiles_out").resolve()


def test_sanitize_profile_label() -> None:
    assert sanitize_profile_label("my profile/test") == "my_profile_test"
    assert sanitize_profile_label("   ") == "profile"


def test_run_cprofile_callable_writes_artifacts(tmp_path: Path) -> None:
    def work(n: int) -> int:
        total = 0
        for idx in range(n):
            total += (idx * idx) % 17
        return total

    result, artifact = run_cprofile_callable(
        work,
        5000,
        label="unit-test-profile",
        profile_dir=tmp_path,
        sort_key="cumulative",
        top_n=20,
    )
    assert isinstance(result, int)
    assert artifact.prof_path.exists()
    assert artifact.summary_path.exists()
    summary = artifact.summary_path.read_text(encoding="utf-8")
    assert "cProfile summary" in summary
    assert "unit-test-profile" in summary
    assert "work" in summary
    rendered = render_pstats_summary_text(artifact.prof_path, top_n=5)
    assert "work" in rendered
