"""Opt-in perf observability capture helpers.

These helpers let benchmark runs capture structured `event=...` log records
from tz-player modules without scraping human-readable log message strings.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

_LOG_RECORD_BASE_FIELDS = frozenset(logging.makeLogRecord({}).__dict__.keys())


@dataclass(frozen=True)
class CapturedPerfEvent:
    """Structured event captured from a log record."""

    logger_name: str
    level: str
    message: str
    event: str
    created_s: float
    context: dict[str, object]


class PerfEventCaptureHandler(logging.Handler):
    """In-memory collector for structured perf events emitted via logging."""

    def __init__(
        self,
        *,
        logger_prefixes: tuple[str, ...] = ("tz_player",),
        event_names: set[str] | None = None,
        levels: set[int] | None = None,
    ) -> None:
        super().__init__()
        self._logger_prefixes = logger_prefixes
        self._event_names = event_names
        self._levels = levels
        self._lock = threading.Lock()
        self._events: list[CapturedPerfEvent] = []

    def emit(self, record: logging.LogRecord) -> None:
        """Collect matching structured events from log records."""
        if self._levels is not None and record.levelno not in self._levels:
            return
        if self._logger_prefixes and not record.name.startswith(self._logger_prefixes):
            return
        event_name = getattr(record, "event", None)
        if not isinstance(event_name, str) or not event_name:
            return
        if self._event_names is not None and event_name not in self._event_names:
            return

        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _LOG_RECORD_BASE_FIELDS and not key.startswith("_")
        }
        captured = CapturedPerfEvent(
            logger_name=record.name,
            level=record.levelname,
            message=record.getMessage(),
            event=event_name,
            created_s=float(record.created),
            context=extras,
        )
        with self._lock:
            self._events.append(captured)

    def snapshot(self) -> list[CapturedPerfEvent]:
        """Return a point-in-time copy of captured events."""
        with self._lock:
            return list(self._events)

    def clear(self) -> None:
        """Clear buffered captured events."""
        with self._lock:
            self._events.clear()


@contextmanager
def capture_perf_events(
    *,
    logger: logging.Logger | None = None,
    logger_prefixes: tuple[str, ...] = ("tz_player",),
    event_names: set[str] | None = None,
    levels: set[int] | None = None,
) -> Iterator[PerfEventCaptureHandler]:
    """Context manager that attaches a temporary perf-event capture handler."""
    target_logger = logger if logger is not None else logging.getLogger()
    handler = PerfEventCaptureHandler(
        logger_prefixes=logger_prefixes,
        event_names=event_names,
        levels=levels,
    )
    target_logger.addHandler(handler)
    try:
        yield handler
    finally:
        target_logger.removeHandler(handler)


def count_events_by_name(events: list[CapturedPerfEvent]) -> dict[str, int]:
    """Return event occurrence counts by event name."""
    counts: dict[str, int] = {}
    for event in events:
        counts[event.event] = counts.get(event.event, 0) + 1
    return counts


def filter_events(
    events: list[CapturedPerfEvent], *, event_name: str | None = None
) -> list[CapturedPerfEvent]:
    """Filter captured events by event name."""
    if event_name is None:
        return list(events)
    return [event for event in events if event.event == event_name]
