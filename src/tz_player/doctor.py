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
    """One environment/tooling readiness check result."""

    name: str
    status: DoctorStatus
    required: bool
    detail: str
    hint: str | None = None


@dataclass(frozen=True)
class DoctorReport:
    """Collection of doctor checks and derived process exit contract."""

    backend: str
    checks: list[DoctorCheck]

    @property
    def exit_code(self) -> int:
        """Return non-zero when any required check failed or is missing."""
        for check in self.checks:
            if check.required and check.status != "ok":
                return 2
        return 0


def run_doctor(backend: str) -> DoctorReport:
    """Run configured diagnostics for selected backend mode."""
    checks = [
        probe_tinytag(),
        probe_vlc(required=backend == "vlc"),
        probe_ffmpeg(required=False),
    ]
    return DoctorReport(backend=backend, checks=checks)


def render_report(report: DoctorReport) -> str:
    """Render terminal-friendly diagnostics report text."""
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
    """Verify TinyTag dependency importability."""
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
    """Verify python-vlc import and libVLC runtime usability."""
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
    except Exception as exc:
        return DoctorCheck(
            name="vlc/libvlc",
            status="error",
            required=required,
            detail=f"python-vlc {version}; libVLC runtime unavailable ({exc.__class__.__name__})",
            hint="Install VLC/libVLC and verify runtime library search path.",
        )
    try:
        # Creating a media player verifies that the runtime bindings are actually usable.
        instance.media_player_new()
    except Exception as exc:
        return DoctorCheck(
            name="vlc/libvlc",
            status="error",
            required=required,
            detail=f"python-vlc {version}; libVLC runtime unavailable ({exc.__class__.__name__})",
            hint="Install VLC/libVLC and verify runtime library search path.",
        )
    release_text = _libvlc_version(vlc, instance)
    return DoctorCheck(
        name="vlc/libvlc",
        status="ok",
        required=required,
        detail=f"python-vlc {version}; libVLC {release_text}",
    )


def probe_ffmpeg(*, required: bool) -> DoctorCheck:
    """Verify ffmpeg binary presence and basic executable health."""
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
    if proc.returncode != 0:
        stderr_first = ""
        if proc.stderr:
            stderr_first = proc.stderr.strip().splitlines()[0]
        detail = f"ffmpeg -version failed (exit={proc.returncode})" + (
            f": {stderr_first}" if stderr_first else ""
        )
        return DoctorCheck(
            name="ffmpeg",
            status="error",
            required=required,
            detail=detail,
            hint="Reinstall ffmpeg and verify PATH.",
        )
    first_line = ""
    if proc.stdout:
        first_line = proc.stdout.strip().splitlines()[0]
    detail = first_line or f"binary found at {ffmpeg}"
    return DoctorCheck(name="ffmpeg", status="ok", required=required, detail=detail)


def _status_token(status: DoctorStatus) -> str:
    """Map doctor status to compact display token."""
    if status == "ok":
        return "[OK]"
    if status == "missing":
        return "[MISS]"
    return "[ERR]"


def _libvlc_version(vlc: object, instance: object) -> str:
    """Best-effort extraction of libVLC runtime version string."""
    candidates = (
        getattr(vlc, "libvlc_get_version", None),
        getattr(instance, "libvlc_get_version", None),
    )
    for getter in candidates:
        if not callable(getter):
            continue
        try:
            release = getter()
        except Exception:
            continue
        if isinstance(release, bytes):
            try:
                return release.decode("utf-8", errors="replace")
            except Exception:
                return "unknown"
        if release:
            return str(release)
    return "detected"
