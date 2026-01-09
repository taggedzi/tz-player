"""Basic smoke tests."""

import tz_player


def test_version_defined() -> None:
    assert isinstance(tz_player.__version__, str)
