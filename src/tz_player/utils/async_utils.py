"""Helpers for running blocking work from async code."""

from __future__ import annotations

import asyncio
import atexit
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, Callable, TypeVar

T = TypeVar("T")

_IO_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tz-player-io")


@atexit.register
def _shutdown_io_executor() -> None:
    _IO_EXECUTOR.shutdown(wait=False, cancel_futures=True)


async def run_blocking(func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Run blocking callables on a dedicated IO executor."""
    loop = asyncio.get_running_loop()
    if kwargs:
        bound = partial(func, *args, **kwargs)
        return await loop.run_in_executor(_IO_EXECUTOR, bound)
    return await loop.run_in_executor(_IO_EXECUTOR, func, *args)
