"""Guided setup flow for required/optional external media tools."""

from __future__ import annotations

import shutil
import subprocess
import sys
import webbrowser

from .doctor import DoctorCheck, probe_ffmpeg, probe_vlc
from .paths import state_path

VLC_WINGET_ID = "VideoLAN.VLC"
FFMPEG_WINGET_ID = "Gyan.FFmpeg"
VLC_DOWNLOAD_URL = "https://www.videolan.org/vlc/"
FFMPEG_DOWNLOAD_URL = "https://ffmpeg.org/download.html"


def run_setup(*, backend: str = "vlc") -> int:
    """Run an interactive setup flow; return exit code."""
    required_vlc = backend == "vlc"
    print("tz-player setup")
    print("")
    print("VLC is required for audio playback.")
    print("FFmpeg is optional and improves visualization responsiveness.")
    print("")

    vlc_check = probe_vlc(required=required_vlc)
    ffmpeg_check = probe_ffmpeg(required=False)

    _render_check(vlc_check)
    _render_check(ffmpeg_check)
    print("")

    if vlc_check.status != "ok":
        if not _handle_vlc_setup(vlc_check):
            _print_manual_instructions(required_vlc=True)
            return 2 if required_vlc else 0
        vlc_check = probe_vlc(required=required_vlc)
        _render_check(vlc_check)
        print("")
        if vlc_check.status != "ok":
            _print_manual_instructions(required_vlc=True)
            return 2 if required_vlc else 0

    if ffmpeg_check.status != "ok" and _handle_ffmpeg_setup(ffmpeg_check):
        ffmpeg_check = probe_ffmpeg(required=False)
        _render_check(ffmpeg_check)
        print("")

    print("Setup complete.")
    print("Optional: configure native helper usage in your state file:")
    print(f"  {state_path()}")
    print("  native_helper_enabled: true|false")
    print("  native_helper_timeout_s: seconds")
    return 0


def _render_check(check: DoctorCheck) -> None:
    state = (
        "OK"
        if check.status == "ok"
        else "MISSING"
        if check.status == "missing"
        else "ERROR"
    )
    req = "required" if check.required else "optional"
    print(f"{state:<7} {check.name} ({req}) - {check.detail}")
    if check.hint:
        print(f"        hint: {check.hint}")


def _handle_vlc_setup(check: DoctorCheck) -> bool:
    print("VLC is required to play audio.")
    return _handle_install(
        name="VLC",
        winget_id=VLC_WINGET_ID,
        download_url=VLC_DOWNLOAD_URL,
        required=True,
        detail=check.detail,
    )


def _handle_ffmpeg_setup(check: DoctorCheck) -> bool:
    print("FFmpeg enables responsive visualizations but is optional.")
    return _handle_install(
        name="FFmpeg",
        winget_id=FFMPEG_WINGET_ID,
        download_url=FFMPEG_DOWNLOAD_URL,
        required=False,
        detail=check.detail,
    )


def _handle_install(
    *, name: str, winget_id: str, download_url: str, required: bool, detail: str
) -> bool:
    print(f"{name} status: {detail}")
    if not _prompt_yes_no(f"Install {name} now?", default=False):
        return False
    if _is_windows() and _has_winget():
        print(f"Running winget install for {name}...")
        return _run_winget_install(winget_id)
    if _prompt_yes_no(f"Open {name} download page in your browser?", default=True):
        return _open_url(download_url)
    if required:
        print(f"{name} install skipped.")
    return False


def _prompt_yes_no(message: str, *, default: bool) -> bool:
    if not sys.stdin.isatty():
        return False
    suffix = " [Y/n]" if default else " [y/N]"
    prompt = f"{message}{suffix}: "
    for _ in range(3):
        try:
            raw = input(prompt)
        except EOFError:
            return False
        response = raw.strip().lower()
        if not response:
            return default
        if response in {"y", "yes"}:
            return True
        if response in {"n", "no"}:
            return False
        print("Please enter y or n.")
    return default


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _has_winget() -> bool:
    return shutil.which("winget") is not None


def _run_winget_install(winget_id: str) -> bool:
    proc = subprocess.run(
        [
            "winget",
            "install",
            "--id",
            winget_id,
            "-e",
            "--accept-package-agreements",
            "--accept-source-agreements",
        ],
        check=False,
    )
    return proc.returncode == 0


def _open_url(url: str) -> bool:
    try:
        return webbrowser.open(url, new=2)
    except Exception:
        return False


def _print_manual_instructions(*, required_vlc: bool) -> None:
    if _is_windows():
        print("Manual install steps (Windows):")
        print(f"- VLC:    winget install {VLC_WINGET_ID}")
        print(f"- FFmpeg: winget install {FFMPEG_WINGET_ID}")
        return
    print("Manual install steps:")
    if required_vlc:
        print("- VLC:    https://www.videolan.org/vlc/")
    print("- FFmpeg: https://ffmpeg.org/download.html")
    print("See docs/media-setup.md for OS-specific package manager commands.")
