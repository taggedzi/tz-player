"""Tests for SQLite lock-retry helper behavior."""

from __future__ import annotations

import sqlite3

import pytest

import tz_player.services.sqlite_retry as sqlite_retry_module
from tz_player.services.sqlite_retry import run_with_sqlite_lock_retry


def test_run_with_sqlite_lock_retry_retries_lock_then_succeeds(monkeypatch) -> None:
    calls = {"count": 0}
    sleeps: list[float] = []

    def fake_sleep(value: float) -> None:
        sleeps.append(value)

    monkeypatch.setattr(sqlite_retry_module.time, "sleep", fake_sleep)
    monkeypatch.setattr(sqlite_retry_module.random, "random", lambda: 0.0)

    def _operation() -> str:
        calls["count"] += 1
        if calls["count"] < 3:
            raise sqlite3.OperationalError("database is locked")
        return "ok"

    result = run_with_sqlite_lock_retry(
        _operation,
        op_name="test.locked",
        max_attempts=4,
        base_delay_s=0.01,
    )

    assert result == "ok"
    assert calls["count"] == 3
    assert len(sleeps) == 2
    assert sleeps[0] >= 0.0
    assert sleeps[1] >= sleeps[0]


def test_run_with_sqlite_lock_retry_does_not_retry_non_lock_errors() -> None:
    calls = {"count": 0}

    def _operation() -> None:
        calls["count"] += 1
        raise sqlite3.OperationalError("no such table: missing_table")

    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        run_with_sqlite_lock_retry(_operation, op_name="test.non_lock")
    assert calls["count"] == 1
