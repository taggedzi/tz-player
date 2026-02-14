# Media Tool Setup

This guide is for users who want real playback (`vlc` backend) and optional non-WAV envelope analysis (`ffmpeg`).

## VLC/libVLC (Playback)

`tz-player --backend vlc` requires VLC/libVLC installed on the system.

Windows:

- `winget install VideoLAN.VLC`

macOS:

- `brew install --cask vlc`

Ubuntu/Debian:

- `sudo apt update && sudo apt install vlc`

Fedora:

- `sudo dnf install vlc`

Arch:

- `sudo pacman -S vlc`

## FFmpeg (Optional Envelope Analysis)

FFmpeg is optional. Without it, only WAV envelope analysis is available; other formats fall back to simulated VU levels.

Windows:

- `winget install Gyan.FFmpeg`

macOS:

- `brew install ffmpeg`

Ubuntu/Debian:

- `sudo apt update && sudo apt install ffmpeg`

Fedora:

- `sudo dnf install ffmpeg`

Arch:

- `sudo pacman -S ffmpeg`

## Verify Tools

```bash
ffmpeg -version
```

```bash
python -c "import vlc; print(vlc.__version__)"
```

```bash
tz-player doctor --backend vlc
```

Recommended verification flow:

1. Install VLC and optional FFmpeg via your package manager.
2. Run `tz-player doctor --backend vlc`.
3. Confirm required checks are `[OK]`.

## Notes

- Keep VLC/FFmpeg as system-installed tools rather than bundling binaries if you want simpler license compliance.
- See `docs/license-compliance.md` for distribution guidance.
