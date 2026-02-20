"""Runtime visualizer host with activation, fallback, and throttling policies."""

from __future__ import annotations

import logging
import time

from .base import VisualizerContext, VisualizerFrameInput, VisualizerPlugin
from .registry import VisualizerRegistry

logger = logging.getLogger(__name__)


class VisualizerHost:
    """Manages visualizer activation, frame rendering, and fallback."""

    def __init__(
        self,
        registry: VisualizerRegistry,
        *,
        target_fps: int = 10,
    ) -> None:
        self._registry = registry
        self._active_id = registry.default_id
        self._active_plugin: VisualizerPlugin | None = None
        self._frame_index = 0
        self._notice: str | None = None
        self._target_fps = max(2, min(target_fps, 30))
        self._budget_s = 1.0 / self._target_fps
        self._overrun_streak = 0
        self._skip_frames = 0

    @property
    def target_fps(self) -> int:
        return self._target_fps

    @property
    def active_id(self) -> str:
        return self._active_id

    @property
    def active_requires_spectrum(self) -> bool:
        plugin = self._active_plugin
        if plugin is None:
            return False
        return bool(getattr(plugin, "requires_spectrum", False))

    @property
    def active_requires_beat(self) -> bool:
        plugin = self._active_plugin
        if plugin is None:
            return False
        return bool(getattr(plugin, "requires_beat", False))

    def activate(self, plugin_id: str | None, context: VisualizerContext) -> str:
        """Activate requested plugin, falling back to default on failure/missing."""
        requested = plugin_id or self._registry.default_id
        if not self._registry.has_plugin(requested):
            self._notice = f"Visualizer '{requested}' unavailable; using '{self._registry.default_id}'."
            logger.warning(self._notice)
            logger.info(
                "Visualizer fallback selected for missing plugin",
                extra={
                    "event": "visualizer_fallback",
                    "requested_plugin_id": requested,
                    "active_plugin_id": self._registry.default_id,
                    "phase": "activate",
                    "reason": "missing_plugin",
                },
            )
            requested = self._registry.default_id

        plugin = self._registry.create(requested)
        if plugin is None:
            requested = self._registry.default_id
            plugin = self._registry.create(requested)
        if plugin is None:
            raise RuntimeError("No usable visualizer plugin is available.")

        if self._active_plugin is not None:
            self._safe_deactivate(self._active_plugin)

        try:
            plugin.on_activate(context)
        except Exception as exc:
            logger.exception("Visualizer '%s' activation failed: %s", requested, exc)
            self._notice = (
                f"Visualizer '{requested}' failed during activate; using fallback."
            )
            logger.info(
                "Visualizer fallback selected after activation failure",
                extra={
                    "event": "visualizer_fallback",
                    "requested_plugin_id": requested,
                    "active_plugin_id": self._registry.default_id,
                    "phase": "activate",
                    "reason": "activation_error",
                },
            )
            fallback = self._registry.create(self._registry.default_id)
            if fallback is None:
                raise RuntimeError("Fallback visualizer unavailable.") from exc
            try:
                fallback.on_activate(context)
            except Exception as fallback_exc:
                raise RuntimeError(
                    "Fallback visualizer activation failed."
                ) from fallback_exc
            plugin = fallback
            requested = self._registry.default_id

        self._active_plugin = plugin
        self._active_id = requested
        logger.info(
            "Visualizer activated",
            extra={
                "event": "visualizer_activated",
                "active_plugin_id": self._active_id,
            },
        )
        return self._active_id

    def shutdown(self) -> None:
        """Deactivate active plugin and release host-managed plugin state."""
        if self._active_plugin is not None:
            self._safe_deactivate(self._active_plugin)
        self._active_plugin = None

    def consume_notice(self) -> str | None:
        """Return and clear one-shot user-facing notice text, if present."""
        notice = self._notice
        self._notice = None
        return notice

    def render_frame(
        self, frame: VisualizerFrameInput, context: VisualizerContext
    ) -> str:
        """Render one frame with fallback safety and budget-based throttling."""
        if self._active_plugin is None:
            self.activate(self._registry.default_id, context)

        if self._skip_frames > 0:
            self._skip_frames -= 1
            return "Visualizer throttled"

        assert self._active_plugin is not None
        start = time.monotonic()
        try:
            output = self._active_plugin.render(frame)
        except Exception as exc:
            failed_id = self._active_id
            logger.exception("Visualizer '%s' render failed: %s", failed_id, exc)
            self._notice = (
                f"Visualizer '{failed_id}' failed during render; using fallback."
            )
            logger.info(
                "Visualizer fallback selected after render failure",
                extra={
                    "event": "visualizer_fallback",
                    "requested_plugin_id": failed_id,
                    "active_plugin_id": self._registry.default_id,
                    "phase": "render",
                    "reason": "render_error",
                },
            )
            self.activate(self._registry.default_id, context)
            assert self._active_plugin is not None
            output = self._active_plugin.render(frame)

        elapsed = time.monotonic() - start
        if elapsed > self._budget_s:
            self._overrun_streak += 1
            if self._overrun_streak >= 3:
                logger.warning(
                    "Visualizer '%s' render overrun %.3fs > %.3fs; throttling one frame",
                    self._active_id,
                    elapsed,
                    self._budget_s,
                )
                self._skip_frames = 1
                self._overrun_streak = 0
        else:
            self._overrun_streak = 0

        self._frame_index += 1
        return output

    @property
    def frame_index(self) -> int:
        return self._frame_index

    def _safe_deactivate(self, plugin: VisualizerPlugin) -> None:
        """Best-effort plugin deactivation that never propagates exceptions."""
        try:
            plugin.on_deactivate()
        except Exception as exc:
            logger.warning("Visualizer deactivate failed: %s", exc)
