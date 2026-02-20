"""Process-isolated visualizer runner for optional hardened plugin mode.

This module runs local visualizer plugins in a separate Python process and
proxies lifecycle/render calls over a simple pipe-based RPC channel.
"""

from __future__ import annotations

import importlib
import importlib.util
import multiprocessing
import sys
from dataclasses import dataclass
from multiprocessing.process import BaseProcess
from pathlib import Path
from types import ModuleType
from typing import Any, Protocol

from .base import VisualizerContext, VisualizerFrameInput


class _ConnLike(Protocol):
    def send(self, obj: Any) -> None: ...
    def recv(self) -> Any: ...
    def poll(self, timeout: float | None = None) -> bool: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class PluginSourceSpec:
    """Describes how to resolve a plugin class at runtime."""

    source_kind: str
    source_value: str
    class_name: str


class IsolatedPluginProxy:
    """Plugin proxy that executes plugin logic in a dedicated subprocess."""

    def __init__(
        self,
        *,
        plugin_id: str,
        display_name: str,
        plugin_api_version: int,
        requires_spectrum: bool,
        requires_beat: bool,
        source: PluginSourceSpec,
        timeout_s: float = 0.25,
        startup_timeout_s: float = 2.0,
    ) -> None:
        self.plugin_id = plugin_id
        self.display_name = display_name
        self.plugin_api_version = plugin_api_version
        self.requires_spectrum = requires_spectrum
        self.requires_beat = requires_beat
        self._source = source
        self._timeout_s = timeout_s
        self._startup_timeout_s = startup_timeout_s
        self._ctx = multiprocessing.get_context("spawn")
        self._conn: _ConnLike | None = None
        self._process: BaseProcess | None = None

    def on_activate(self, context: VisualizerContext) -> None:
        self._ensure_started()
        self._request("activate", {"context": context}, timeout_s=self._timeout_s)

    def on_deactivate(self) -> None:
        if self._process is None:
            return
        try:
            self._request("deactivate", {}, timeout_s=self._timeout_s)
        finally:
            self._shutdown_worker()

    def render(self, frame: VisualizerFrameInput) -> str:
        self._ensure_started()
        result = self._request("render", {"frame": frame}, timeout_s=self._timeout_s)
        return str(result)

    def _ensure_started(self) -> None:
        if (
            self._process is not None
            and self._process.is_alive()
            and self._conn is not None
        ):
            return
        self._shutdown_worker()
        parent_conn, child_conn = self._ctx.Pipe(duplex=True)
        process = self._ctx.Process(
            target=_isolated_worker,
            args=(
                child_conn,
                self._source.source_kind,
                self._source.source_value,
                self._source.class_name,
                self.plugin_id,
            ),
            daemon=True,
        )
        process.start()
        self._conn = parent_conn
        self._process = process
        self._request("ping", {}, timeout_s=self._startup_timeout_s)

    def _shutdown_worker(self) -> None:
        conn = self._conn
        process = self._process
        self._conn = None
        self._process = None
        if conn is not None:
            try:
                if process is not None and process.is_alive():
                    conn.send({"op": "shutdown", "payload": {}})
            except (BrokenPipeError, EOFError, OSError):
                pass
            finally:
                conn.close()
        if process is not None:
            process.join(timeout=0.1)
            if process.is_alive():
                process.terminate()
                process.join(timeout=0.2)

    def _request(self, op: str, payload: dict[str, Any], *, timeout_s: float) -> Any:
        conn = self._conn
        process = self._process
        if conn is None or process is None:
            raise RuntimeError("Isolated plugin runner is not available.")
        if not process.is_alive():
            raise RuntimeError("Isolated plugin runner exited unexpectedly.")

        try:
            conn.send({"op": op, "payload": payload})
        except (BrokenPipeError, EOFError, OSError) as exc:
            self._shutdown_worker()
            raise RuntimeError(
                "Failed to send request to isolated plugin runner."
            ) from exc

        if not conn.poll(timeout_s):
            self._shutdown_worker()
            raise RuntimeError(f"Isolated plugin runner timed out during '{op}'.")

        try:
            response = conn.recv()
        except (BrokenPipeError, EOFError, OSError) as exc:
            self._shutdown_worker()
            raise RuntimeError(
                "Failed to receive response from isolated plugin runner."
            ) from exc

        if not isinstance(response, dict):
            raise RuntimeError(
                "Isolated plugin runner returned invalid response payload."
            )
        if response.get("ok"):
            return response.get("result")
        message = str(response.get("error", "unknown isolated runner error"))
        raise RuntimeError(message)


def _isolated_worker(
    conn: _ConnLike,
    source_kind: str,
    source_value: str,
    class_name: str,
    expected_plugin_id: str,
) -> None:
    plugin: Any = None
    try:
        plugin_class = _load_plugin_class(
            source_kind=source_kind,
            source_value=source_value,
            class_name=class_name,
        )
        plugin = plugin_class()
        plugin_id = getattr(plugin, "plugin_id", None)
        if plugin_id != expected_plugin_id:
            raise RuntimeError(
                f"Plugin ID mismatch in isolated runner: expected '{expected_plugin_id}', got '{plugin_id}'."
            )
    except Exception as exc:
        _safe_send(conn, {"ok": False, "error": f"Isolated plugin load failed: {exc}"})
        conn.close()
        return

    while True:
        try:
            message = conn.recv()
        except EOFError:
            break
        if not isinstance(message, dict):
            _safe_send(conn, {"ok": False, "error": "Invalid worker request payload."})
            continue
        op = message.get("op")
        payload = message.get("payload", {})
        if op == "shutdown":
            _safe_send(conn, {"ok": True, "result": None})
            break
        if op == "ping":
            _safe_send(conn, {"ok": True, "result": "pong"})
            continue

        try:
            if op == "activate":
                plugin.on_activate(payload["context"])
                _safe_send(conn, {"ok": True, "result": None})
            elif op == "deactivate":
                plugin.on_deactivate()
                _safe_send(conn, {"ok": True, "result": None})
            elif op == "render":
                result = plugin.render(payload["frame"])
                _safe_send(conn, {"ok": True, "result": result})
            else:
                _safe_send(conn, {"ok": False, "error": f"Unknown worker op '{op}'."})
        except Exception as exc:
            _safe_send(
                conn, {"ok": False, "error": f"Plugin worker operation failed: {exc}"}
            )

    conn.close()


def _safe_send(conn: _ConnLike, response: dict[str, Any]) -> None:
    try:
        conn.send(response)
    except (BrokenPipeError, EOFError, OSError):
        return


def _load_plugin_class(
    *, source_kind: str, source_value: str, class_name: str
) -> type[Any]:
    if source_kind == "import":
        module = importlib.import_module(source_value)
    elif source_kind == "file":
        path = Path(source_value)
        module = _load_module_from_file(path)
    else:
        raise RuntimeError(f"Unsupported plugin source kind '{source_kind}'.")

    plugin_class = getattr(module, class_name, None)
    if plugin_class is None:
        raise RuntimeError(
            f"Plugin class '{class_name}' not found in source '{source_value}'."
        )
    if not isinstance(plugin_class, type):
        raise RuntimeError(
            f"Plugin class '{class_name}' in '{source_value}' is not a class object."
        )
    return plugin_class


def _load_module_from_file(path: Path) -> ModuleType:
    module_name = f"tz_player.isolated_visualizer_{abs(hash(str(path)))}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to build module spec for '{path}'.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
