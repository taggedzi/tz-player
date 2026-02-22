"""Tests for SQLite waveform-proxy cache lookup and invalidation behavior."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from tz_player.services.waveform_proxy_store import (
    SqliteWaveformProxyStore,
    WaveformProxyParams,
)


def _run(coro):
    return asyncio.run(coro)


def _touch(path: Path, content: bytes = b"x") -> None:
    path.write_bytes(content)


def test_waveform_proxy_store_cache_hit_and_nearest_lookup(tmp_path) -> None:
    db_path = tmp_path / "library.sqlite"
    store = SqliteWaveformProxyStore(db_path)
    _run(store.initialize())

    track = tmp_path / "song.mp3"
    _touch(track, b"abcdef")
    params = WaveformProxyParams(hop_ms=20)

    _run(
        store.upsert_waveform_proxy(
            track,
            duration_ms=1000,
            params=params,
            frames=[
                (0, -20, 40, -30, 35),
                (1000, -10, 55, -12, 60),
            ],
        )
    )

    assert _run(store.has_waveform_proxy(track, params=params)) is True
    sample = _run(store.get_frame_at(track, position_ms=400, params=params))
    assert sample is not None
    assert sample.min_left_i8 == -20
    assert sample.max_right_i8 == 35

    tail = _run(store.get_frame_at(track, position_ms=2000, params=params))
    assert tail is not None
    assert tail.max_left_i8 == 55
    assert tail.min_right_i8 == -12


def test_waveform_proxy_store_miss_when_fingerprint_changes(tmp_path) -> None:
    db_path = tmp_path / "library.sqlite"
    store = SqliteWaveformProxyStore(db_path)
    _run(store.initialize())

    track = tmp_path / "song.mp3"
    _touch(track, b"abcdef")
    params = WaveformProxyParams(hop_ms=20)

    _run(
        store.upsert_waveform_proxy(
            track,
            duration_ms=1000,
            params=params,
            frames=[(0, -20, 20, -20, 20)],
        )
    )
    assert _run(store.get_frame_at(track, position_ms=0, params=params)) is not None

    _touch(track, b"abcdef-ghij")
    assert _run(store.get_frame_at(track, position_ms=0, params=params)) is None
    assert _run(store.has_waveform_proxy(track, params=params)) is False


def test_waveform_proxy_store_get_frame_does_not_write_access_timestamp(
    tmp_path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    store = SqliteWaveformProxyStore(db_path)
    _run(store.initialize())

    track = tmp_path / "song.mp3"
    _touch(track, b"abcdef")
    params = WaveformProxyParams(hop_ms=20)

    _run(
        store.upsert_waveform_proxy(
            track,
            duration_ms=1000,
            params=params,
            frames=[(0, -20, 20, -10, 10)],
        )
    )

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE analysis_cache_entries SET last_accessed_at = 100 WHERE analysis_type = 'waveform_proxy'"
        )

    sample = _run(store.get_frame_at(track, position_ms=0, params=params))
    assert sample is not None

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT last_accessed_at FROM analysis_cache_entries WHERE analysis_type = 'waveform_proxy' LIMIT 1"
        ).fetchone()
    assert row is not None
    assert int(row[0]) == 100
