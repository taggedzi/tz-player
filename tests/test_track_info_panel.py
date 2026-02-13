"""Tests for current-track information panel formatting."""

from __future__ import annotations

from rich.text import Text

from tz_player.app import _format_track_info_panel
from tz_player.services.player_service import TrackInfo


def test_format_track_info_panel_with_track() -> None:
    text = _format_track_info_panel(
        TrackInfo(
            title="Song",
            artist="Artist",
            album="Album",
            year=2026,
            path="/tmp/song.mp3",
            duration_ms=123000,
            genre="Synthwave",
            bitrate_kbps=320,
        )
    )
    assert isinstance(text, Text)
    assert "Title: Song" in text.plain
    assert "Artist: Artist | Genre: Synthwave" in text.plain
    assert "Album: Album | Year: 2026" in text.plain
    assert "Time: 02:03 | Bitrate: 320 kbps" in text.plain
    assert any("bold" in (span.style or "") for span in text.spans)


def test_format_track_info_panel_without_track() -> None:
    text = _format_track_info_panel(None)
    assert isinstance(text, Text)
    assert text.plain == (
        "Title: --\nArtist: --\nAlbum: -- | Year: ----\nTime: --:-- | Bitrate: --"
    )
