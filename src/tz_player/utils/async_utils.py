"""Async utility helpers for safely offloading blocking callables.

This module provides the project-wide thread-pool bridge used to keep the
Textual event loop responsive during file/DB/metadata operations.
"""

from __future__ import annotations

import asyncio
import atexit
from concurrent.futures import Executor, ThreadPoolExecutor
from functools import partial
from typing import Any, Callable, TypeVar

T = TypeVar("T")

_IO_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tz-player-io")
_CPU_EXECUTOR: ThreadPoolExecutor | None = ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="tz-player-cpu"
)
_CPU_EXECUTOR_UNAVAILABLE = False


@atexit.register
def _shutdown_io_executor() -> None:
    _IO_EXECUTOR.shutdown(wait=False, cancel_futures=True)
    if _CPU_EXECUTOR is not None:
        _CPU_EXECUTOR.shutdown(wait=False, cancel_futures=True)


async def run_blocking(func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Run blocking callable on dedicated IO executor and await its result."""
    return await _run_on_executor(_IO_EXECUTOR, func, *args, **kwargs)


async def run_cpu_blocking(func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Run CPU-heavy callable on dedicated CPU executor and await its result."""
    cpu_executor = _resolve_cpu_executor()
    return await _run_on_executor(cpu_executor, func, *args, **kwargs)


async def run_cpu_bound(func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Backward-compatible alias for `run_cpu_blocking`."""
    return await run_cpu_blocking(func, *args, **kwargs)


async def _run_on_executor(
    executor: Executor,
    func: Callable[..., T],
    /,
    *args: Any,
    **kwargs: Any,
) -> T:
    """Run callable on selected executor and await result with timeout polling."""
    if not callable(func):
        raise TypeError("func must be callable")
    loop = asyncio.get_running_loop()
    if kwargs:
        bound = partial(func, *args, **kwargs)
        future = loop.run_in_executor(executor, bound)
    else:
        future = loop.run_in_executor(executor, func, *args)
    # Some environments can miss thread->loop wakeups for executor completion.
    # Polling with a short timeout keeps completion deterministic.
    while True:
        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout=0.1)
        except asyncio.TimeoutError:
            continue


def _resolve_cpu_executor() -> Executor:
    """Return CPU executor with IO fallback when unavailable."""
    if _CPU_EXECUTOR_UNAVAILABLE or _CPU_EXECUTOR is None:
        return _IO_EXECUTOR
    return _CPU_EXECUTOR
