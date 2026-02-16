# tz-player

[![CI](https://github.com/taggedzi/tz-player/actions/workflows/ci.yml/badge.svg)](https://github.com/taggedzi/tz-player/actions)
![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)
![Platform: Linux](https://img.shields.io/badge/platform-linux-lightgrey)
![Platform: Windows](https://img.shields.io/badge/platform-windows-lightgrey)
![Platform: macOS (untested)](https://img.shields.io/badge/platform-macOS-untested-yellow)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

A clean, keyboard-driven music player for the terminal.

`tz-player` is a simple TUI music player built with Python and powered by VLC.
If VLC can play it, `tz-player` can play it.

No streaming.
No accounts.
No background services.
Just your music, in your terminal.

## Screenshots

![Cover Art Screenshot](/docs/images/tz-player_cover-ascii-art_screenshot.png)

![Hackscope Screenshot](/docs/images/tz-player_hackscope_screenshot.png)

![VU Meter Screenshot](/docs/images/tz-player_vu-meter_screenshot.png)

---

## Platform Support

* ✅ Tested on Linux
* ✅ Tested on Windows
* ⚠️ Expected to work on macOS (Python + VLC), but not officially tested

The goal is full cross-platform support anywhere Python and VLC are available.
macOS support is intended, but cannot be guaranteed due to lack of testing hardware.

---

## Python Version Support

`tz-player` supports:

* Python 3.9 through current stable releases

(3.9 is the lowest supported version. Newer versions should work as Python itself evolves.)

---

## Why Use tz-player?

Because sometimes you just want:

* A fast music player that starts instantly
* Full keyboard control
* A clean terminal interface
* A local-first tool that doesn’t phone home
* Something lightweight that stays out of your way

`tz-player` is built for people who live in the terminal and prefer tools that feel direct and responsive.

It does not try to be Spotify.
It does not try to manage your entire media library.
It just plays your music well.

---

# Requirements

## 1. VLC (Required)

`tz-player` uses VLC (libVLC) for playback.

You must have VLC installed on your system for real audio playback.

If VLC is not installed or not found, the player cannot play music.

Install VLC from:

[https://www.videolan.org/vlc/](https://www.videolan.org/vlc/)

---

# Installation

At the moment, `tz-player` is not published to PyPI.

Clone the repository:

```bash
git clone https://github.com/taggedzi/tz-player.git
cd tz-player
```

Create a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

Install:

```bash
pip install -e .
```

Run:

```bash
tz-player
```

---

# What Can It Play?

Anything VLC can play.

That includes:

* MP3
* FLAC
* WAV
* OGG
* M4A
* AAC
* And many more formats and codecs

VLC handles decoding. `tz-player` handles the interface.

---

# Basic Usage

Launch:

```bash
tz-player
```

On startup the player:

* Restores your last playlist
* Restores playback settings
* Focuses the playlist immediately

You can start navigating right away.

---

## Keyboard Controls

### Playlist Navigation

| Key           | Action                                  |
| ------------- | --------------------------------------- |
| ↑ / ↓         | Move cursor                             |
| Shift + ↑ / ↓ | Reorder item                            |
| v             | Select item                             |
| Delete        | Remove selected (confirmation required) |
| a             | Playlist actions menu                   |
| f             | Focus search                            |

---

### Playback Controls

| Key              | Action                |
| ---------------- | --------------------- |
| Space            | Play / Pause          |
| n                | Next track            |
| p                | Previous track        |
| x                | Stop                  |
| Seek keys        | Move within track     |
| Volume keys      | Adjust volume         |
| Speed keys       | Change playback speed |
| Repeat / Shuffle | Toggle modes          |

You do not need to leave the keyboard to control playback.

---

## Search

Press:

```
f
```

Type to filter your playlist.

* Enter returns focus to the playlist.
* Escape exits search.
* You are never trapped in a search box.

---

## Visualizers

`tz-player` includes a visualizer pane on the right side.

* Visualizers update during playback.
* Plugins are supported.
* If a visualizer fails, the player switches to a safe default automatically.
* Visualizers never interrupt playback.

This keeps the interface stable even if a plugin misbehaves.

---

## Logging and Troubleshooting

Run with:

```bash
tz-player --backend vlc --verbose
```

Or write logs to a file:

```bash
tz-player --backend vlc --log-file player.log
```

Useful flags:

* `--backend vlc` (default; explicit override if needed)
* `--verbose`
* `--quiet`
* `--log-file <path>`

If something fails, error messages explain what happened and what to check.

---

# For Developers

This section is for contributors and future maintainers.

---

## Development Setup

```bash
git clone https://github.com/taggedzi/tz-player.git
cd tz-player
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

---

## Quality Checks

Before committing:

```bash
python -m ruff check .
python -m ruff format --check .
python -m mypy src
python -m pytest
```

Or:

```bash
nox -s lint typecheck tests
```

---

## Architecture Overview

* Source code: `src/tz_player`
* TUI built with Textual
* SQLite for playlists and metadata
* JSON for UI state
* Playback handled through a backend abstraction
* VLC backend provides real audio playback
* Visualizers loaded through a plugin registry

Blocking IO is kept off the UI loop to prevent interface freezes.

---

## Runtime Configuration

Configuration precedence:

1. CLI flags
2. Saved state
3. Built-in defaults

If VLC fails to initialize, the app reports the error clearly and exits with a non-zero code.

---

## Testing Expectations

Tests cover:

* Keyboard navigation
* Focus transitions
* Playlist mutation
* State persistence
* Visualizer loading and fallback behavior

No test should hang indefinitely.

Workflow acceptance is documented in `docs/workflow-acceptance.md`.

---

# License

MIT License
See `LICENSE` and `THIRD_PARTY_LICENSES.md`.

---

# Closing

`tz-player` exists for people who prefer simple, local tools.

If you want:

* A terminal-native music player
* Full keyboard control
* Reliable VLC playback
* No accounts, no cloud, no noise

This is for you.
