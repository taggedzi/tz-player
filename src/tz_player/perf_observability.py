"""Opt-in perf observability capture helpers.

These helpers let benchmark runs capture structured `event=...` log records
from tz-player modules without scraping human-readable log message strings.
"""

from __future__ import annotations

import asyncio
import gc
import inspect
import logging
import statistics
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import wraps
from typing import Any

_resource: Any
try:
    import resource as _resource
except Exception:  # pragma: no cover - platform dependent
    _resource = None

_LOG_RECORD_BASE_FIELDS = frozenset(logging.makeLogRecord({}).__dict__.keys())


@dataclass(frozen=True)
class CapturedPerfEvent:
    """Structured event captured from a log record."""

    logger_name: str
    level: str
    message: str
    event: str
    created_s: float
    captured_monotonic_s: float
    context: dict[str, object]


@dataclass(frozen=True)
class CallProbeStat:
    """Aggregated timing/count stats for a probed method."""

    name: str
    count: int
    total_s: float
    max_s: float

    @property
    def mean_s(self) -> float:
        if self.count <= 0:
            return 0.0
        return self.total_s / self.count


@dataclass(frozen=True)
class ProcessResourceSnapshot:
    """Best-effort process resource sample for perf trend reporting."""

    label: str
    captured_monotonic_s: float
    process_cpu_s: float
    thread_cpu_s: float | None
    gc_counts: tuple[int, int, int]
    gc_collections_total: int | None
    rss_bytes: int | None


@dataclass(frozen=True)
class ProcessResourceDelta:
    """Delta between two resource snapshots."""

    start_label: str
    end_label: str
    elapsed_s: float
    process_cpu_s: float
    thread_cpu_s: float | None
    gc_count_deltas: tuple[int, int, int]
    gc_collections_delta: int | None
    rss_bytes_delta: int | None


@dataclass(frozen=True)
class NumericEventContextSummary:
    """Summary stats for numeric values extracted from event context."""

    event_name: str
    context_key: str
    count: int
    min_value: float
    mean_value: float
    max_value: float


@dataclass(frozen=True)
class EventContextCountSpec:
    """Request to count events grouped by a context field."""

    event_name: str
    context_key: str
    alias: str | None = None


@dataclass(frozen=True)
class EventNumericSummarySpec:
    """Request to summarize numeric event context values."""

    event_name: str
    context_key: str
    alias: str | None = None
    context_equals: dict[str, object] | None = None


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
            captured_monotonic_s=time.perf_counter(),
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


def event_latency_ms_since(start_monotonic_s: float, event: CapturedPerfEvent) -> float:
    """Return latency in ms from monotonic start time to captured event time."""
    return max(
        0.0, (float(event.captured_monotonic_s) - float(start_monotonic_s)) * 1000.0
    )


def find_captured_event(
    events: list[CapturedPerfEvent],
    *,
    event_name: str | None = None,
    context_equals: dict[str, object] | None = None,
) -> CapturedPerfEvent | None:
    """Return the first captured event matching event name and context fields."""
    for event in events:
        if event_name is not None and event.event != event_name:
            continue
        if context_equals:
            matched = True
            for key, value in context_equals.items():
                if event.context.get(key) != value:
                    matched = False
                    break
            if not matched:
                continue
        return event
    return None


def count_events_by_context_value(
    events: list[CapturedPerfEvent],
    *,
    context_key: str,
    event_name: str | None = None,
) -> dict[str, int]:
    """Count events grouped by a string context field."""
    counts: dict[str, int] = {}
    for event in events:
        if event_name is not None and event.event != event_name:
            continue
        value = event.context.get(context_key)
        if not isinstance(value, str) or not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return counts


def summarize_numeric_event_context(
    events: list[CapturedPerfEvent],
    *,
    event_name: str,
    context_key: str,
    context_equals: dict[str, object] | None = None,
) -> NumericEventContextSummary | None:
    """Summarize numeric values for a specific event/context field."""
    values: list[float] = []
    for event in events:
        if event.event != event_name:
            continue
        if context_equals:
            matched = True
            for key, value in context_equals.items():
                if event.context.get(key) != value:
                    matched = False
                    break
            if not matched:
                continue
        raw = event.context.get(context_key)
        if isinstance(raw, (int, float)):
            values.append(float(raw))
    if not values:
        return None
    return NumericEventContextSummary(
        event_name=event_name,
        context_key=context_key,
        count=len(values),
        min_value=min(values),
        mean_value=statistics.fmean(values),
        max_value=max(values),
    )


def summarize_captured_events(
    events: list[CapturedPerfEvent],
    *,
    context_count_specs: list[EventContextCountSpec] | None = None,
    numeric_summary_specs: list[EventNumericSummarySpec] | None = None,
) -> dict[str, object]:
    """Build an artifact-ready summary for a set of captured perf events."""
    context_counts: dict[str, dict[str, int]] = {}
    numeric_summaries: dict[str, dict[str, object]] = {}

    for spec in context_count_specs or []:
        key = spec.alias or f"{spec.event_name}.{spec.context_key}"
        context_counts[key] = count_events_by_context_value(
            events,
            event_name=spec.event_name,
            context_key=spec.context_key,
        )

    for num_spec in numeric_summary_specs or []:
        key = num_spec.alias or f"{num_spec.event_name}.{num_spec.context_key}"
        summary = summarize_numeric_event_context(
            events,
            event_name=num_spec.event_name,
            context_key=num_spec.context_key,
            context_equals=num_spec.context_equals,
        )
        numeric_summaries[key] = (
            {}
            if summary is None
            else {
                "event_name": summary.event_name,
                "context_key": summary.context_key,
                "count": summary.count,
                "min_value": summary.min_value,
                "mean_value": summary.mean_value,
                "max_value": summary.max_value,
            }
        )

    return {
        "event_counts": count_events_by_name(events),
        "context_counts": context_counts,
        "numeric_summaries": numeric_summaries,
    }


async def wait_for_captured_event(
    handler: PerfEventCaptureHandler,
    *,
    event_name: str,
    timeout_s: float = 2.0,
    poll_interval_s: float = 0.01,
    context_equals: dict[str, object] | None = None,
) -> CapturedPerfEvent:
    """Wait for a matching captured event from a capture handler."""
    deadline = time.monotonic() + max(0.0, float(timeout_s))
    interval = max(0.001, float(poll_interval_s))
    while time.monotonic() < deadline:
        event = find_captured_event(
            handler.snapshot(),
            event_name=event_name,
            context_equals=context_equals,
        )
        if event is not None:
            return event
        await asyncio.sleep(interval)
    details = f"event={event_name}"
    if context_equals:
        details = f"{details} context={context_equals}"
    raise TimeoutError(f"Timed out waiting for captured perf {details}")


def capture_process_resource_snapshot(*, label: str) -> ProcessResourceSnapshot:
    """Capture a best-effort process resource snapshot using stdlib only."""
    thread_cpu: float | None
    try:
        thread_cpu = time.thread_time()
    except Exception:  # pragma: no cover - platform dependent
        thread_cpu = None

    gc_collections_total: int | None = None
    try:
        stats = gc.get_stats()
        gc_collections_total = int(sum(int(gen.get("collections", 0)) for gen in stats))
    except Exception:  # pragma: no cover - interpreter dependent
        gc_collections_total = None

    rss_bytes: int | None = None
    if _resource is not None:
        try:
            usage = _resource.getrusage(_resource.RUSAGE_SELF)
            rss_raw = int(getattr(usage, "ru_maxrss", 0))
            # Linux reports KiB; macOS/BSD may report bytes. Heuristic only.
            rss_bytes = rss_raw * 1024 if rss_raw < (1 << 40) else rss_raw
        except Exception:  # pragma: no cover - platform dependent
            rss_bytes = None

    counts = gc.get_count()
    return ProcessResourceSnapshot(
        label=label,
        captured_monotonic_s=time.perf_counter(),
        process_cpu_s=time.process_time(),
        thread_cpu_s=thread_cpu,
        gc_counts=(int(counts[0]), int(counts[1]), int(counts[2])),
        gc_collections_total=gc_collections_total,
        rss_bytes=rss_bytes,
    )


def diff_process_resource_snapshots(
    start: ProcessResourceSnapshot, end: ProcessResourceSnapshot
) -> ProcessResourceDelta:
    """Compute delta between two process resource snapshots."""
    thread_cpu_delta: float | None = None
    if start.thread_cpu_s is not None and end.thread_cpu_s is not None:
        thread_cpu_delta = end.thread_cpu_s - start.thread_cpu_s
    gc_collections_delta: int | None = None
    if start.gc_collections_total is not None and end.gc_collections_total is not None:
        gc_collections_delta = end.gc_collections_total - start.gc_collections_total
    rss_delta: int | None = None
    if start.rss_bytes is not None and end.rss_bytes is not None:
        rss_delta = end.rss_bytes - start.rss_bytes
    return ProcessResourceDelta(
        start_label=start.label,
        end_label=end.label,
        elapsed_s=end.captured_monotonic_s - start.captured_monotonic_s,
        process_cpu_s=end.process_cpu_s - start.process_cpu_s,
        thread_cpu_s=thread_cpu_delta,
        gc_count_deltas=(
            end.gc_counts[0] - start.gc_counts[0],
            end.gc_counts[1] - start.gc_counts[1],
            end.gc_counts[2] - start.gc_counts[2],
        ),
        gc_collections_delta=gc_collections_delta,
        rss_bytes_delta=rss_delta,
    )


class MethodCallProbe:
    """Wrap selected object methods and collect frequency x wall-time stats."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: dict[str, int] = {}
        self._totals: dict[str, float] = {}
        self._maxima: dict[str, float] = {}
        self._restores: list[tuple[object, str, Any]] = []

    def wrap(self, obj: object, attr_name: str, *, alias: str | None = None) -> bool:
        """Wrap one method on `obj`; return `False` if missing/not callable."""
        if not hasattr(obj, attr_name):
            return False
        original = getattr(obj, attr_name)
        if not callable(original):
            return False
        key = alias or f"{obj.__class__.__name__}.{attr_name}"

        def _record(elapsed_s: float) -> None:
            with self._lock:
                self._counts[key] = self._counts.get(key, 0) + 1
                self._totals[key] = self._totals.get(key, 0.0) + elapsed_s
                current_max = self._maxima.get(key, 0.0)
                if elapsed_s > current_max:
                    self._maxima[key] = elapsed_s

        if inspect.iscoroutinefunction(original):

            @wraps(original)
            async def async_wrapper(*args: Any, **kwargs: Any):
                start = time.perf_counter()
                try:
                    return await original(*args, **kwargs)
                finally:
                    _record(time.perf_counter() - start)

            replacement = async_wrapper
        else:

            @wraps(original)
            def sync_wrapper(*args: Any, **kwargs: Any):
                start = time.perf_counter()
                try:
                    return original(*args, **kwargs)
                finally:
                    _record(time.perf_counter() - start)

            replacement = sync_wrapper

        self._restores.append((obj, attr_name, original))
        setattr(obj, attr_name, replacement)
        return True

    def snapshot(self) -> list[CallProbeStat]:
        """Return probe stats sorted by cumulative time descending."""
        with self._lock:
            names = sorted(
                self._counts,
                key=lambda name: self._totals.get(name, 0.0),
                reverse=True,
            )
            return [
                CallProbeStat(
                    name=name,
                    count=self._counts.get(name, 0),
                    total_s=self._totals.get(name, 0.0),
                    max_s=self._maxima.get(name, 0.0),
                )
                for name in names
            ]

    def restore(self) -> None:
        """Restore all wrapped methods."""
        for obj, attr_name, original in reversed(self._restores):
            setattr(obj, attr_name, original)
        self._restores.clear()


@contextmanager
def probe_method_calls(
    targets: list[tuple[object, str, str | None]],
) -> Iterator[MethodCallProbe]:
    """Temporarily wrap methods and collect call/timing stats."""
    probe = MethodCallProbe()
    try:
        for obj, attr_name, alias in targets:
            probe.wrap(obj, attr_name, alias=alias)
        yield probe
    finally:
        probe.restore()
