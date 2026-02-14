"""Runtime diagnostics for external tooling and backend readiness."""

from __future__ import annotations

import importlib
import shutil
import subprocess
from dataclasses import dataclass
from typing import Literal

DoctorStatus = Literal["ok", "missing", "error"]

MEDIA_SETUP_URL = "docs/media-setup.md"


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: DoctorStatus
    required: bool
    detail: str
    hint: str | None = None


@dataclass(frozen=True)
class DoctorReport:
    backend: str
    checks: list[DoctorCheck]

    @property
    def exit_code(self) -> int:
        for check in self.checks:
            if check.required and check.status != "ok":
                return 2
        return 0


def run_doctor(backend: str) -> DoctorReport:
    checks = [
        probe_tinytag(),
        probe_vlc(required=backend == "vlc"),
        probe_ffmpeg(required=False),
    ]
    return DoctorReport(backend=backend, checks=checks)


def render_report(report: DoctorReport) -> str:
    lines = [f"tz-player doctor (backend={report.backend})", ""]
    for check in report.checks:
        state = _status_token(check.status)
        req = "required" if check.required else "optional"
        lines.append(f"{state} {check.name:<11} [{req}] {check.detail}")
        if check.hint:
            lines.append(f"      hint: {check.hint}")
    lines.append("")
    if report.exit_code == 0:
        lines.append("Result: OK")
    else:
        lines.append("Result: FAIL")
        lines.append(f"Install guidance: {MEDIA_SETUP_URL}")
    return "\n".join(lines)


def probe_tinytag() -> DoctorCheck:
    try:
        module = importlib.import_module("tinytag")
    except Exception as exc:
        return DoctorCheck(
            name="tinytag",
            status="missing",
            required=True,
            detail=f"not importable ({exc.__class__.__name__})",
            hint="Install Python dependencies (pip install tz-player).",
        )
    version = getattr(module, "__version__", None)
    detail = f"importable ({version})" if version else "importable"
    return DoctorCheck(name="tinytag", status="ok", required=True, detail=detail)


def probe_vlc(*, required: bool) -> DoctorCheck:
    try:
        vlc = importlib.import_module("vlc")
    except Exception as exc:
        return DoctorCheck(
            name="vlc/libvlc",
            status="missing",
            required=required,
            detail=f"python-vlc import failed ({exc.__class__.__name__})",
            hint="Install VLC/libVLC and ensure python-vlc can locate libVLC.",
        )
    version = getattr(vlc, "__version__", "unknown")
    try:
        instance = vlc.Instance()
        release = instance.libvlc_get_version()
    except Exception as exc:
        return DoctorCheck(
            name="vlc/libvlc",
            status="error",
            required=required,
            detail=f"python-vlc {version}; libVLC runtime unavailable ({exc.__class__.__name__})",
            hint="Install VLC/libVLC and verify runtime library search path.",
        )
    release_text = str(release) if release else "unknown"
    return DoctorCheck(
        name="vlc/libvlc",
        status="ok",
        required=required,
        detail=f"python-vlc {version}; libVLC {release_text}",
    )


def probe_ffmpeg(*, required: bool) -> DoctorCheck:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return DoctorCheck(
            name="ffmpeg",
            status="missing",
            required=required,
            detail="binary not found on PATH",
            hint="Install ffmpeg for non-WAV envelope analysis support.",
        )
    try:
        proc = subprocess.run(
            [ffmpeg, "-version"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except Exception as exc:
        return DoctorCheck(
            name="ffmpeg",
            status="error",
            required=required,
            detail=f"launch failed ({exc.__class__.__name__})",
            hint="Reinstall ffmpeg and verify PATH.",
        )
    first_line = ""
    if proc.stdout:
        first_line = proc.stdout.strip().splitlines()[0]
    detail = first_line or f"binary found at {ffmpeg}"
    return DoctorCheck(name="ffmpeg", status="ok", required=required, detail=detail)


def _status_token(status: DoctorStatus) -> str:
    if status == "ok":
        return "[OK]"
    if status == "missing":
        return "[MISS]"
    return "[ERR]"
