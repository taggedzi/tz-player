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
- `a`: open/toggle the Actions menu (Add files/folder, clear, metadata actions)
- `f`: focus the Find input
- `enter` (in Find): return focus to playlist
- `space`: play/pause
- `n` / `p`: next/previous track
- `x`: stop
- `left` / `right`: seek -5s / +5s
- `shift+left` / `shift+right`: seek -30s / +30s
- `home` / `end`: seek to start/end
- `-` / `+`: volume down/up
- `shift+-` / `shift+=`: volume down/up by 10
- `[` / `]`: speed down/up
- `\`: speed reset to 1.0
- `r`: cycle repeat mode
- `s`: toggle shuffle
- `escape`: dismiss modal/popup; in Find it clears query and exits Find mode

Status pane controls:
- Click or drag the TIME bar to seek.
- Click or drag the VOL and SPD bars to change volume and speed.
- Time display shows MM:SS normally and switches to H:MM:SS for long tracks.

Playlist footer:
- Track counter shows `Track: ####/####` (current/total).
- Repeat indicator shows `R:OFF|ONE|ALL` and shuffle shows `S:OFF|ON`.
- Transport buttons allow Prev/Play/Pause/Stop/Next with mouse clicks.

Find/filter behavior:
- Typing in Find filters playlist rows by metadata/path text.
- Empty query restores the full playlist view.
- Escape priority is deterministic: popup/modal dismisses first, then Find exits/clears.
- Playback keys are available from main UI focus states (playlist pane, viewport, footer controls).
