"""Logging helpers."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


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

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric)
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)
