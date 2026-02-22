from __future__ import annotations

import logging

from tz_player.perf_observability import (
    capture_perf_events,
    count_events_by_name,
    filter_events,
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
