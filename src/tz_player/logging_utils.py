"""Logging helpers."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path


class JsonLogFormatter(logging.Formatter):
    """Structured JSON formatter for log file output."""

    _reserved = {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "taskName",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extras = {
            key: _json_safe(value)
            for key, value in record.__dict__.items()
            if key not in self._reserved and not key.startswith("_")
        }
        if extras:
            payload["context"] = extras
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def _json_safe(value: object) -> object:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}
    return repr(value)


def setup_logging(
    log_dir: Path,
    level: str | int = "INFO",
    max_bytes: int = 1_000_000,
    backup_count: int = 3,
    log_file: Path | None = None,
) -> None:
    """Configure rotating file and console logging."""
    if isinstance(level, str):
        numeric = logging.getLevelName(level.upper())
        if isinstance(numeric, str):
            numeric = logging.INFO
    else:
        numeric = level

    if log_file is None:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "tz-player.log"
    else:
        log_path = log_file
        log_path.parent.mkdir(parents=True, exist_ok=True)

    file_formatter = JsonLogFormatter()
    stream_formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(file_formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(stream_formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric)
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)
