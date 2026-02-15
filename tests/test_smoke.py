"""Basic smoke tests."""

import tz_player
import tz_player.version


def test_version_defined() -> None:
    assert isinstance(tz_player.__version__, str)


def test_version_single_source_of_truth() -> None:
    assert tz_player.__version__ == tz_player.version.__version__
