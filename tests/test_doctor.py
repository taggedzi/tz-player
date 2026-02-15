"""Tests for environment diagnostics probes and report behavior."""

from __future__ import annotations

import types

import tz_player.doctor as doctor_module


def test_run_doctor_fake_backend_allows_missing_vlc(monkeypatch) -> None:
    monkeypatch.setattr(
        doctor_module, "probe_tinytag", lambda: _check("tinytag", "ok", True)
    )
    monkeypatch.setattr(
        doctor_module,
        "probe_vlc",
        lambda **kwargs: _check("vlc/libvlc", "missing", kwargs["required"]),
    )
    monkeypatch.setattr(
        doctor_module,
        "probe_ffmpeg",
        lambda **kwargs: _check("ffmpeg", "missing", kwargs["required"]),
    )

    report = doctor_module.run_doctor("fake")
    assert report.exit_code == 0


def test_run_doctor_vlc_backend_fails_when_vlc_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        doctor_module, "probe_tinytag", lambda: _check("tinytag", "ok", True)
    )
    monkeypatch.setattr(
        doctor_module,
        "probe_vlc",
        lambda **kwargs: _check("vlc/libvlc", "missing", kwargs["required"]),
    )
    monkeypatch.setattr(
        doctor_module,
        "probe_ffmpeg",
        lambda **kwargs: _check("ffmpeg", "ok", kwargs["required"]),
    )

    report = doctor_module.run_doctor("vlc")
    assert report.exit_code == 2


def test_probe_ffmpeg_missing(monkeypatch) -> None:
    monkeypatch.setattr(doctor_module.shutil, "which", lambda _name: None)
    check = doctor_module.probe_ffmpeg(required=False)
    assert check.status == "missing"
    assert check.required is False


def test_probe_ffmpeg_nonzero_version_exit_is_error(monkeypatch) -> None:
    monkeypatch.setattr(doctor_module.shutil, "which", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(
        doctor_module.subprocess,
        "run",
        lambda *args, **kwargs: types.SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="ffmpeg: broken install",
        ),
    )
    check = doctor_module.probe_ffmpeg(required=False)
    assert check.status == "error"
    assert "exit=1" in check.detail


def test_probe_tinytag_ok(monkeypatch) -> None:
    fake = types.SimpleNamespace(__version__="9.9.9")
    monkeypatch.setattr(doctor_module.importlib, "import_module", lambda name: fake)
    check = doctor_module.probe_tinytag()
    assert check.status == "ok"
    assert "9.9.9" in check.detail


def test_render_report_includes_result_and_hint() -> None:
    report = doctor_module.DoctorReport(
        backend="vlc",
        checks=[
            _check("tinytag", "ok", True),
            doctor_module.DoctorCheck(
                name="vlc/libvlc",
                status="missing",
                required=True,
                detail="missing",
                hint="install vlc",
            ),
        ],
    )
    text = doctor_module.render_report(report)
    assert "Result: FAIL" in text
    assert "Install guidance:" in text
    assert "install vlc" in text


def _check(name: str, status: str, required: bool) -> doctor_module.DoctorCheck:
    return doctor_module.DoctorCheck(
        name=name,
        status=status,  # type: ignore[arg-type]
        required=required,
        detail="detail",
    )
