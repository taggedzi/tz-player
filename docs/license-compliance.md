# License Compliance Notes

This project is licensed under MIT. Third-party components keep their own licenses.

This document is practical guidance, not legal advice.

## Current Runtime Dependencies

From `pyproject.toml`:

- `textual` (MIT)
- `platformdirs` (MIT)
- `python-vlc` (LGPL-2.1-or-later)
- `mutagen` (GPL-2.0-or-later)

The `mutagen` license is the primary licensing risk for MIT-only distribution goals.

## External Tools

- VLC/libVLC: required for `--backend vlc`
- FFmpeg: optional for non-WAV envelope analysis

Recommended compliance posture:

- Do not bundle VLC/libVLC binaries in your wheel.
- Do not bundle FFmpeg binaries in your wheel.
- Require users to install these tools separately.
- Document that these tools are optional/externally installed where applicable.

## What This Means for MIT

- Your repository can remain MIT-licensed.
- Third-party dependencies/tools do not change the text of your MIT license file.
- Distribution obligations may still apply based on what you ship together.

Key concern in current state:

- `mutagen` is GPL-2.0-or-later. If your distribution policy requires avoiding GPL runtime dependencies, replace `mutagen` with a permissive alternative before release.

## Safe Distribution Checklist

1. Keep project `LICENSE` as MIT.
2. Include `THIRD_PARTY_LICENSES.md` in repository and release artifacts.
3. Keep VLC/FFmpeg external (user-installed), not bundled.
4. If shipping binaries/installers, document exactly which third-party components are included.
5. If GPL dependencies are unacceptable for your policy, remove/replace them before publishing.

## Primary Sources

- FFmpeg legal and licensing: https://www.ffmpeg.org/legal.html
- VLC legal information: https://www.videolan.org/legal.html
- libVLC overview: https://www.videolan.org/vlc/libvlc.html
- Python VLC binding: https://pypi.org/project/python-vlc/
- Mutagen (license metadata): https://pypi.org/project/mutagen/
