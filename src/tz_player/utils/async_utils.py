"""Async utility helpers for safely offloading blocking callables.

This module provides:
- a thread-pool bridge (`run_blocking`) for IO-heavy operations, and
- a process-pool bridge (`run_cpu_bound`) for CPU-heavy work that can hold
  the GIL long enough to starve the UI loop.
"""

from __future__ import annotations

import asyncio
import atexit
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from functools import partial
from typing import Any, Callable, TypeVar

T = TypeVar("T")

_IO_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tz-player-io")
_CPU_EXECUTOR: ProcessPoolExecutor | None = None
_CPU_EXECUTOR_UNAVAILABLE = False


@atexit.register
def _shutdown_io_executor() -> None:
    _IO_EXECUTOR.shutdown(wait=False, cancel_futures=True)
    if _CPU_EXECUTOR is not None:
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
    """Run CPU-heavy callable on dedicated process pool and await its result."""
    global _CPU_EXECUTOR, _CPU_EXECUTOR_UNAVAILABLE
    if not callable(func):
        raise TypeError("func must be callable")

    if not _CPU_EXECUTOR_UNAVAILABLE and _CPU_EXECUTOR is None:
        try:
            _CPU_EXECUTOR = ProcessPoolExecutor(
                max_workers=1,
                mp_context=mp.get_context("spawn"),
            )
        except (OSError, PermissionError):
            _CPU_EXECUTOR_UNAVAILABLE = True

    if _CPU_EXECUTOR_UNAVAILABLE or _CPU_EXECUTOR is None:
        return await run_blocking(func, *args, **kwargs)

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
