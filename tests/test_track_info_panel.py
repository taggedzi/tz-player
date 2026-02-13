"""Tests for current-track information panel formatting."""

from __future__ import annotations

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
        )
    )
    assert "Title: Song" in text
    assert "Artist: Artist" in text
    assert "Album: Album" in text
    assert "Time: 02:03" in text


def test_format_track_info_panel_without_track() -> None:
    text = _format_track_info_panel(None)
    assert text == "Title: --\nArtist: --\nAlbum: --\nTime: --:--"
