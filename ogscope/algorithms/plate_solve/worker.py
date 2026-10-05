"""共享的单线程图像解算工作池 / Shared single-worker image-solving executor."""

from __future__ import annotations

import asyncio
import contextvars
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, Callable, TypeVar

_Result = TypeVar("_Result")
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="solver")


def get_solver_executor() -> ThreadPoolExecutor:
    """所有解算入口复用同一个工作线程 / Reuse one worker across solving entry points."""
    return _executor


async def run_solver_job(
    function: Callable[..., _Result], *args: Any, **kwargs: Any
) -> _Result:
    """保留上下文并串行执行；取消等待不会并发启动下一次解算。

    Preserve context and serialize jobs; cancelling a waiter cannot overlap
    the next solve with the native work still running in the worker.
    """
    context = contextvars.copy_context()
    call = partial(context.run, function, *args, **kwargs)
    return await asyncio.get_running_loop().run_in_executor(_executor, call)
