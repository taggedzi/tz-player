"""Tests for SQLite envelope cache lookup/interpolation."""

from __future__ import annotations

import asyncio
from pathlib import Path

from tz_player.services.audio_envelope_store import SqliteEnvelopeStore


def _run(coro):
    return asyncio.run(coro)


def _touch(path: Path, content: bytes = b"x") -> None:
    path.write_bytes(content)


def test_envelope_store_cache_hit_and_interpolation(tmp_path) -> None:
    db_path = tmp_path / "library.sqlite"
    store = SqliteEnvelopeStore(db_path)
    _run(store.initialize())

    track = tmp_path / "song.mp3"
    _touch(track, b"abcdef")

    _run(
        store.upsert_envelope(
            track,
            [
                (0, 0.0, 0.0),
                (1000, 1.0, 0.5),
            ],
            duration_ms=1000,
        )
    )

    sample = _run(store.get_level_at(str(track), 500))
    assert sample is not None
    assert round(sample.left, 2) == 0.50
    assert round(sample.right, 2) == 0.25


def test_envelope_store_miss_when_fingerprint_changes(tmp_path) -> None:
    db_path = tmp_path / "library.sqlite"
    store = SqliteEnvelopeStore(db_path)
    _run(store.initialize())

    track = tmp_path / "song.mp3"
    _touch(track, b"abcdef")

    _run(
        store.upsert_envelope(
            track,
            [
                (0, 0.2, 0.2),
                (1000, 0.8, 0.8),
            ],
            duration_ms=1000,
        )
    )

    assert _run(store.get_level_at(str(track), 200)) is not None

    # Change fingerprint by mutating file content/size.
    _touch(track, b"abcdefXYZ")
    assert _run(store.get_level_at(str(track), 200)) is None


def test_envelope_store_out_of_range_uses_nearest_sample(tmp_path) -> None:
    db_path = tmp_path / "library.sqlite"
    store = SqliteEnvelopeStore(db_path)
    _run(store.initialize())

    track = tmp_path / "song.mp3"
    _touch(track, b"1234")

    _run(
        store.upsert_envelope(
            track,
            [
                (100, 0.1, 0.2),
                (300, 0.3, 0.4),
            ],
            duration_ms=300,
        )
    )

    before = _run(store.get_level_at(str(track), 0))
    after = _run(store.get_level_at(str(track), 1000))
    assert before is not None
    assert after is not None
    assert round(before.left, 2) == 0.10
    assert round(after.right, 2) == 0.40
