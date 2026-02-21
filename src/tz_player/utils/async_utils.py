"""Async utility helpers for safely offloading blocking callables.

This module provides project-wide executor bridges used to keep the Textual
event loop responsive:
- `run_blocking(...)` for IO-bound tasks (file/database/metadata reads),
- `run_cpu_bound(...)` for heavier CPU-oriented analysis work.
"""

from __future__ import annotations

import asyncio
import atexit
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, Callable, TypeVar

T = TypeVar("T")

_IO_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tz-player-io")
_CPU_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tz-player-cpu")


@atexit.register
def _shutdown_io_executor() -> None:
    _IO_EXECUTOR.shutdown(wait=False, cancel_futures=True)
    _CPU_EXECUTOR.shutdown(wait=False, cancel_futures=True)


async def run_blocking(func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Run blocking callable on dedicated IO executor and await its result."""
    if not callable(func):
        raise TypeError("func must be callable")
    loop = asyncio.get_running_loop()
    if kwargs:
        bound = partial(func, *args, **kwargs)
        future = loop.run_in_executor(_IO_EXECUTOR, bound)
    else:
        future = loop.run_in_executor(_IO_EXECUTOR, func, *args)
    # Some environments can miss thread->loop wakeups for executor completion.
    # Polling with a short timeout keeps completion deterministic.
    while True:
        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout=0.1)
        except asyncio.TimeoutError:
            continue


async def run_cpu_bound(func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Run CPU-heavy callable on dedicated executor and await its result."""
    if not callable(func):
        raise TypeError("func must be callable")
    loop = asyncio.get_running_loop()
    if kwargs:
        bound = partial(func, *args, **kwargs)
        future = loop.run_in_executor(_CPU_EXECUTOR, bound)
    else:
        future = loop.run_in_executor(_CPU_EXECUTOR, func, *args)
    while True:
        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout=0.1)
        except asyncio.TimeoutError:
            continue
