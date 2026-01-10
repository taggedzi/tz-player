# Usage

Run the TUI:

```
python -m tz_player.app
```

Select a playback backend:

```
python -m tz_player.app --backend vlc
```

Notes:
- Default backend is `fake`.
- The VLC backend requires VLC/libVLC installed on your system.

GUI entrypoint supports the same flag:

```
python -m tz_player.gui --backend vlc
```

Current keys:
- `up` / `down`: move cursor up/down in the playlist
- `shift+up` / `shift+down`: reorder selection up/down
- `v`: toggle selection for the current row
- `delete`: remove selected tracks (confirm)
- `f`: focus the Find input
- `space`: play/pause
- `n` / `p`: next/previous track
- `x`: stop
- `left` / `right`: seek -5s / +5s
- `home` / `end`: seek to start/end
- `-` / `+`: volume down/up
- `[` / `]`: speed down/up
- `\`: speed reset to 1.0
- `r`: cycle repeat mode
- `s`: toggle shuffle
- `escape`: dismiss modals
