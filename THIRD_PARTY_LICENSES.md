# Third-Party Licenses

This file summarizes major third-party licenses used by `tz-player`.

This summary is informational and not legal advice.

## Runtime Python Dependencies

- textual
  - License: MIT
  - Source: https://pypi.org/project/textual/

- platformdirs
  - License: MIT
  - Source: https://pypi.org/project/platformdirs/

- python-vlc
  - License: LGPL-2.1-or-later
  - Source: https://pypi.org/project/python-vlc/

- tinytag
  - License: MIT
  - Source: https://pypi.org/project/tinytag/

- Pillow
  - License: HPND (historical PIL license)
  - Source: https://pypi.org/project/Pillow/

## Development Dependencies

- pytest
  - License: MIT
  - Source: https://pypi.org/project/pytest/

- ruff
  - License: MIT
  - Source: https://pypi.org/project/ruff/

- mypy
  - License: MIT (mypy/mypyc), Apache-2.0 (typeshed)
  - Source: https://pypi.org/project/mypy/

- nox
  - License: Apache-2.0
  - Source: https://pypi.org/project/nox/

## Required External Tools

- VLC/libVLC (system-installed for real playback backend)
  - License family: LGPL/GPL components (see VideoLAN legal pages)
  - Source: https://www.videolan.org/legal.html
  - libVLC: https://www.videolan.org/vlc/libvlc.html

## Optional External Tools

- FFmpeg (system-installed, optional for non-WAV envelope analysis)
  - License: LGPL 2.1+ or GPL 2+ depending build configuration
  - Source: https://www.ffmpeg.org/legal.html

## Notes

- Project license remains MIT (`LICENSE`).
- Third-party software keeps its own license terms.
- If distributing bundled binaries/installers, review each included component license carefully.
