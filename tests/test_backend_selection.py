"""Tests for playback backend selection."""

from __future__ import annotations

from tz_player.app import _resolve_backend_name


def test_backend_selection_defaults_to_fake() -> None:
    assert _resolve_backend_name(None, None) == "fake"


def test_backend_selection_cli_overrides_state() -> None:
    assert _resolve_backend_name("vlc", "fake") == "vlc"
    assert _resolve_backend_name("fake", "vlc") == "fake"


def test_backend_selection_state_fallback() -> None:
    assert _resolve_backend_name(None, "vlc") == "vlc"
    assert _resolve_backend_name("invalid", "vlc") == "vlc"
    assert _resolve_backend_name(None, "invalid") == "fake"


def test_backend_selection_normalizes_case_and_whitespace() -> None:
    assert _resolve_backend_name(" VLC ", "fake") == "vlc"
    assert _resolve_backend_name(None, "  Fake  ") == "fake"
