"""相机任务与原生工作回执的唯一所有者 / Sole owner of camera tasks and native completion receipts."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable


class CameraResources:
    """取消等待者不能丢失原生完成证据 / Waiter cancellation cannot discard native completion receipts."""

    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)
        # 固定采集线程，避免原生图像缓存散落到默认线程池 / Pin capture to one worker to bound native image caches.
        self.capture_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="camera-capture"
        )
        self.jpeg_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="ogscope-jpeg"
        )
        self.background_tasks: set[asyncio.Task] = set()
        self.worker_futures: set[asyncio.Future] = set()
        self.executors_closed = False

    def spawn(self, coroutine: Coroutine[Any, Any, Any]) -> asyncio.Task:
        """保留任务直到真正结束，包括已取消的计时器 / Retain tasks until completion, including cancelled timers."""
        task = asyncio.create_task(coroutine)
        self.background_tasks.add(task)

        def finished(done: asyncio.Task) -> None:
            self.background_tasks.discard(done)
            if not done.cancelled() and done.exception() is not None:
                self._logger.warning(
                    "相机后台任务失败 / Camera background task failed: %s",
                    done.exception(),
                )

        task.add_done_callback(finished)
        return task

    def submit(
        self, executor: ThreadPoolExecutor | None, fn: Callable, *args: Any
    ) -> asyncio.Future:
        """跟踪原生工作，调用方取消不能取消这份完成证据 / Track native completion independently of caller cancellation."""
        if self.executors_closed:
            raise RuntimeError("相机工作线程已关闭 / Camera workers are closed")
        future = asyncio.get_running_loop().run_in_executor(executor, fn, *args)
        self.worker_futures.add(future)

        def finished(done: asyncio.Future) -> None:
            self.worker_futures.discard(done)
            if not done.cancelled():
                done.exception()

        future.add_done_callback(finished)
        return future

    async def run(
        self, executor: ThreadPoolExecutor | None, fn: Callable, *args: Any
    ) -> Any:
        """屏蔽等待者取消，保留原生完成回执 / Shield the worker's completion receipt from waiter cancellation."""
        return await asyncio.shield(self.submit(executor, fn, *args))

    def close_executors(self) -> None:
        """封闭提交入口，不阻塞事件循环等待原生线程 / Seal submissions without joining native threads on the event loop."""
        self.executors_closed = True
        self.capture_executor.shutdown(wait=False, cancel_futures=True)
        self.jpeg_executor.shutdown(wait=False, cancel_futures=True)
