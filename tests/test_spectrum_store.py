"""Tests for SQLite spectrum cache lookup and retention pruning."""

from __future__ import annotations

import asyncio
from pathlib import Path

from tz_player.services.spectrum_store import SpectrumParams, SqliteSpectrumStore


def _run(coro):
    return asyncio.run(coro)


def _touch(path: Path, content: bytes = b"x") -> None:
    path.write_bytes(content)


def test_spectrum_store_cache_hit_and_nearest_lookup(tmp_path) -> None:
    db_path = tmp_path / "library.sqlite"
    store = SqliteSpectrumStore(db_path)
    _run(store.initialize())

    track = tmp_path / "song.mp3"
    _touch(track, b"abcdef")
    params = SpectrumParams(band_count=4, hop_ms=40)

    _run(
        store.upsert_spectrum(
            track,
            duration_ms=1000,
            params=params,
            frames=[
                (0, bytes([1, 2, 3, 4])),
                (1000, bytes([9, 8, 7, 6])),
            ],
        )
    )

    assert _run(store.has_spectrum(track, params=params)) is True
    sample = _run(store.get_frame_at(track, position_ms=400, params=params))
    assert sample is not None
    assert sample.bands == bytes([1, 2, 3, 4])

    tail = _run(store.get_frame_at(track, position_ms=2000, params=params))
    assert tail is not None
    assert tail.bands == bytes([9, 8, 7, 6])


def test_spectrum_store_miss_when_fingerprint_changes(tmp_path) -> None:
    db_path = tmp_path / "library.sqlite"
    store = SqliteSpectrumStore(db_path)
    _run(store.initialize())

    track = tmp_path / "song.mp3"
    _touch(track, b"abcdef")
    params = SpectrumParams(band_count=4, hop_ms=40)

    _run(
        store.upsert_spectrum(
            track,
            duration_ms=1000,
            params=params,
            frames=[(0, bytes([1, 2, 3, 4]))],
        )
    )
    assert _run(store.get_frame_at(track, position_ms=0, params=params)) is not None

    _touch(track, b"abcdef-ghij")
    assert _run(store.get_frame_at(track, position_ms=0, params=params)) is None
    assert _run(store.has_spectrum(track, params=params)) is False


def test_spectrum_store_prune_enforces_size_limit(tmp_path) -> None:
    db_path = tmp_path / "library.sqlite"
    store = SqliteSpectrumStore(db_path)
    _run(store.initialize())

    params = SpectrumParams(band_count=4, hop_ms=40)
    for idx in range(3):
        track = tmp_path / f"song-{idx}.mp3"
        _touch(track, f"payload-{idx}".encode())
        _run(
            store.upsert_spectrum(
                track,
                duration_ms=1000,
                params=params,
                frames=[(0, bytes([idx, idx, idx, idx]))],
            )
        )

    pruned = _run(
        store.prune(
            max_cache_bytes=4,
            max_age_days=365,
            min_recent_tracks_protected=0,
        )
    )
    assert pruned >= 2


def test_spectrum_store_throttles_access_touch_writes(tmp_path) -> None:
    db_path = tmp_path / "library.sqlite"
    store = SqliteSpectrumStore(db_path)
    _run(store.initialize())

    track = tmp_path / "song.mp3"
    _touch(track, b"abcdef")
    params = SpectrumParams(band_count=4, hop_ms=40)
    _run(
        store.upsert_spectrum(
            track,
            duration_ms=1000,
            params=params,
            frames=[(0, bytes([1, 2, 3, 4]))],
        )
    )

    assert _run(store.get_frame_at(track, position_ms=0, params=params)) is not None
    touched_once = dict(store._last_access_touch_s)  # noqa: SLF001
    assert len(touched_once) == 1

    assert _run(store.get_frame_at(track, position_ms=20, params=params)) is not None
    assert store._last_access_touch_s == touched_once  # noqa: SLF001

    store._access_touch_interval_s = -1.0  # noqa: SLF001
    assert _run(store.get_frame_at(track, position_ms=40, params=params)) is not None
    assert len(store._last_access_touch_s) == 1  # noqa: SLF001
    assert next(iter(store._last_access_touch_s.values())) > next(
        iter(touched_once.values())
    )  # noqa: SLF001
