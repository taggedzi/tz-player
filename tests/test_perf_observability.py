from __future__ import annotations

import logging
import time

from tz_player.perf_observability import (
    capture_perf_events,
    capture_process_resource_snapshot,
    count_events_by_name,
    diff_process_resource_snapshots,
    event_latency_ms_since,
    filter_events,
    probe_method_calls,
)


def test_capture_perf_events_collects_structured_event_logs() -> None:
    root = logging.getLogger()
    logger = logging.getLogger("tz_player.test_perf")
    prior_level = root.level
    root.setLevel(logging.INFO)
    try:
        with capture_perf_events(logger=root) as handler:
            logger.info(
                "Visualizer frame loop overrun",
                extra={
                    "event": "visualizer_frame_loop_overrun",
                    "elapsed_s": 0.12,
                    "frame_budget_s": 0.07,
                },
            )
            logger.info("plain info without event")
            events = handler.snapshot()

        assert len(events) == 1
        event = events[0]
        assert event.event == "visualizer_frame_loop_overrun"
        assert event.logger_name == "tz_player.test_perf"
        assert event.captured_monotonic_s > 0
        assert event.context["elapsed_s"] == 0.12
        assert event.context["frame_budget_s"] == 0.07
        assert count_events_by_name(events) == {"visualizer_frame_loop_overrun": 1}
    finally:
        root.setLevel(prior_level)


def test_capture_perf_events_filters_by_event_name_and_logger_prefix() -> None:
    root = logging.getLogger()
    prior_level = root.level
    root.setLevel(logging.INFO)
    try:
        with capture_perf_events(
            logger=root,
            logger_prefixes=("tz_player.services",),
            event_names={"analysis_preload_completed"},
        ) as handler:
            logging.getLogger("tz_player.services.player_service").info(
                "Analysis preload completed",
                extra={"event": "analysis_preload_completed", "elapsed_s": 0.2},
            )
            logging.getLogger("tz_player.app").info(
                "Visualizer frame loop overrun",
                extra={"event": "visualizer_frame_loop_overrun", "elapsed_s": 0.3},
            )
            logging.getLogger("tz_player.services.spectrum_service").info(
                "Spectrum sampling stats",
                extra={"event": "spectrum_sampling_stats", "memory_hits": 10},
            )
            events = handler.snapshot()
        assert [event.event for event in events] == ["analysis_preload_completed"]
        assert filter_events(events, event_name="analysis_preload_completed") == events
    finally:
        root.setLevel(prior_level)


def test_capture_perf_events_context_manager_detaches_handler() -> None:
    root = logging.getLogger()
    initial_handler_count = len(root.handlers)
    with capture_perf_events(logger=root):
        assert len(root.handlers) == initial_handler_count + 1
    assert len(root.handlers) == initial_handler_count


def test_probe_method_calls_collects_sync_method_stats() -> None:
    class Sample:
        def __init__(self) -> None:
            self.value = 0

        def bump(self, amount: int) -> int:
            time.sleep(0.001)
            self.value += amount
            return self.value

    sample = Sample()
    with probe_method_calls([(sample, "bump", "sample.bump")]) as probe:
        assert sample.bump(1) == 1
        assert sample.bump(2) == 3
        stats = probe.snapshot()

    assert len(stats) == 1
    stat = stats[0]
    assert stat.name == "sample.bump"
    assert stat.count == 2
    assert stat.total_s > 0
    assert stat.max_s > 0
    assert stat.mean_s > 0


def test_probe_method_calls_collects_async_method_stats() -> None:
    import asyncio

    class Sample:
        async def work(self) -> str:
            await asyncio.sleep(0.001)
            return "ok"

    async def run() -> None:
        sample = Sample()
        with probe_method_calls([(sample, "work", "sample.work")]) as probe:
            assert await sample.work() == "ok"
            assert await sample.work() == "ok"
            stats = probe.snapshot()
        assert len(stats) == 1
        assert stats[0].name == "sample.work"
        assert stats[0].count == 2
        assert stats[0].total_s > 0

    asyncio.run(run())


def test_capture_process_resource_snapshot_and_delta() -> None:
    start = capture_process_resource_snapshot(label="start")
    for _ in range(20_000):
        _ = 123 * 456
    end = capture_process_resource_snapshot(label="end")
    delta = diff_process_resource_snapshots(start, end)

    assert start.label == "start"
    assert end.label == "end"
    assert delta.start_label == "start"
    assert delta.end_label == "end"
    assert delta.elapsed_s >= 0
    assert delta.process_cpu_s >= 0
    assert len(delta.gc_count_deltas) == 3


def test_event_latency_ms_since_uses_monotonic_time() -> None:
    root = logging.getLogger()
    prior_level = root.level
    root.setLevel(logging.INFO)
    try:
        with capture_perf_events(logger=root) as handler:
            start = time.perf_counter()
            logging.getLogger("tz_player.test_perf").info(
                "Analysis preload completed",
                extra={"event": "analysis_preload_completed"},
            )
            event = handler.snapshot()[0]
        latency_ms = event_latency_ms_since(start, event)
        assert latency_ms >= 0.0
        assert latency_ms < 1000.0
    finally:
        root.setLevel(prior_level)
