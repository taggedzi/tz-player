"""SQLite lock-retry helpers for transient writer contention."""

from __future__ import annotations

import random
import sqlite3
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

_LOCKED_TOKENS = ("database is locked", "database is busy", "locked", "busy")


def run_with_sqlite_lock_retry(
    operation: Callable[[], T],
    *,
    op_name: str,
    max_attempts: int = 4,
    base_delay_s: float = 0.02,
    max_delay_s: float = 0.25,
) -> T:
    """Run SQLite operation with bounded retry/backoff on transient lock errors."""
    attempts = max(1, int(max_attempts))
    delay = max(0.0, float(base_delay_s))
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except sqlite3.OperationalError as exc:
            message = str(exc).lower()
            is_lock_error = any(token in message for token in _LOCKED_TOKENS)
            if not is_lock_error or attempt >= attempts:
                raise
            jitter = random.random() * delay * 0.5 if delay > 0 else 0.0
            sleep_for = min(max_delay_s, delay + jitter)
            time.sleep(max(0.0, sleep_for))
            delay = min(max_delay_s, max(0.005, delay * 2.0))
    raise RuntimeError(f"SQLite retry loop exhausted unexpectedly for {op_name}")
