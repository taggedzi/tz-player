"""Tests for SQLite beat cache lookup and fingerprint invalidation."""

from __future__ import annotations

import asyncio
from pathlib import Path

from tz_player.services.beat_store import BeatParams, SqliteBeatStore


def _run(coro):
    return asyncio.run(coro)


def _touch(path: Path, content: bytes = b"x") -> None:
    path.write_bytes(content)


def test_beat_store_cache_hit_and_nearest_lookup(tmp_path) -> None:
    db_path = tmp_path / "library.sqlite"
    store = SqliteBeatStore(db_path)
    _run(store.initialize())

    track = tmp_path / "song.mp3"
    _touch(track, b"abcdef")
    params = BeatParams(hop_ms=40)

    _run(
        store.upsert_beats(
            track,
            duration_ms=1000,
            params=params,
            bpm=123.0,
            frames=[
                (0, 10, False),
                (1000, 220, True),
            ],
        )
    )

    assert _run(store.has_beats(track, params=params)) is True
    sample = _run(store.get_frame_at(track, position_ms=400, params=params))
    assert sample is not None
    assert sample.strength_u8 == 10
    assert sample.is_beat is False
    assert sample.bpm == 123.0

    tail = _run(store.get_frame_at(track, position_ms=2000, params=params))
    assert tail is not None
    assert tail.strength_u8 == 220
    assert tail.is_beat is True
    assert tail.bpm == 123.0


def test_beat_store_miss_when_fingerprint_changes(tmp_path) -> None:
    db_path = tmp_path / "library.sqlite"
    store = SqliteBeatStore(db_path)
    _run(store.initialize())

    track = tmp_path / "song.mp3"
    _touch(track, b"abcdef")
    params = BeatParams(hop_ms=40)

    _run(
        store.upsert_beats(
            track,
            duration_ms=1000,
            params=params,
            bpm=110.0,
            frames=[(0, 42, False)],
        )
    )
    assert _run(store.get_frame_at(track, position_ms=0, params=params)) is not None

    _touch(track, b"abcdef-ghij")
    assert _run(store.get_frame_at(track, position_ms=0, params=params)) is None
    assert _run(store.has_beats(track, params=params)) is False
