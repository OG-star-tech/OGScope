"""
相机 MJPEG 流共享实现 / Shared camera MJPEG streaming implementation.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Coroutine
from typing import Any

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from starlette.requests import Request

from ogscope.config import get_settings
from ogscope.domain.camera.services import camera_domain_service
from ogscope.domain.camera.stream_limiter import (
    MjpegStreamLease,
    get_mjpeg_stream_limiter,
)
from ogscope.web.camera_shared import get_camera_manager
from ogscope.web.mjpeg_stream_helpers import mjpeg_sleep_or_disconnect

_cleanup_tasks: set[asyncio.Task[Any]] = set()
_module_logger = logging.getLogger(__name__)


def _finish_cleanup_task(task: asyncio.Task[Any]) -> None:
    """移除并读取清理结果，避免遗失后台异常 / Remove the task and consume background errors."""
    _cleanup_tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        _module_logger.error(
            "mjpeg_cleanup_failed error=%s",
            exc,
            exc_info=(type(exc), exc, exc.__traceback__),
        )


def _retain_cleanup_task(coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
    """保留清理任务直至完成，避免调用方取消中断资源回收 / Retain cleanup across caller cancellation."""
    task = asyncio.create_task(coro)
    _cleanup_tasks.add(task)
    task.add_done_callback(_finish_cleanup_task)
    return task


class _MjpegStreamSession:
    """统一持有流租约与相机消费者 / Own the stream lease and camera consumer together."""

    def __init__(
        self,
        *,
        lease: MjpegStreamLease,
        manager: Any,
        stall_timeout_s: float,
        logger: logging.Logger,
        path: str,
    ) -> None:
        self._lease = lease
        self._manager = manager
        self._stall_timeout_s = max(0.0, stall_timeout_s)
        self._logger = logger
        self._path = path
        self._preview_acquired = False
        self._closed = False
        self._cleanup_task: asyncio.Task[Any] | None = None
        self._watchdog_task: asyncio.Task[Any] | None = None

    @property
    def closed(self) -> bool:
        return self._closed

    def start_watchdog(self) -> None:
        """在响应开始前启动发送停滞看门狗 / Start the send-stall watchdog before response iteration."""
        if self._stall_timeout_s > 0 and self._watchdog_task is None:
            self._watchdog_task = asyncio.create_task(self._watch_for_stall())

    async def acquire_preview_consumer(self) -> bool:
        """获取相机消费者，并处理获取期间发生的超时 / Acquire camera consumer safely across timeout."""
        await self._manager.acquire_preview_consumer()
        if self._closed:
            task = _retain_cleanup_task(self._manager.release_preview_consumer())
            await asyncio.shield(task)
            return False
        self._preview_acquired = True
        return True

    async def touch(self) -> None:
        """仅在上一帧已完成 ASGI 发送后刷新进展 / Refresh progress only after the prior ASGI send completed."""
        await self._lease.touch()

    async def close(self, reason: str = "response_complete") -> None:
        """幂等关闭；独立清理任务可跨越调用方取消 / Close idempotently in a cancellation-safe task."""
        if self._cleanup_task is None:
            self._closed = True
            self._cleanup_task = _retain_cleanup_task(self._close_once(reason))
        await asyncio.shield(self._cleanup_task)

    async def _close_once(self, reason: str) -> None:
        watchdog = self._watchdog_task
        current = asyncio.current_task()
        if watchdog is not None and watchdog is not current:
            watchdog.cancel()

        # 先释放并发租约，再等待相机停止 / Release the slot before awaiting camera shutdown.
        released = await self._lease.release(reason)
        if released:
            self._logger.info(
                "mjpeg_session_released reason=%s path=%s", reason, self._path
            )

        if self._preview_acquired:
            self._preview_acquired = False
            await self._manager.release_preview_consumer()

    async def _watch_for_stall(self) -> None:
        interval = min(1.0, max(0.05, self._stall_timeout_s / 4.0))
        try:
            while not self._closed:
                await asyncio.sleep(interval)
                idle_s = await self._lease.idle_seconds()
                if idle_s is None:
                    return
                if idle_s >= self._stall_timeout_s:
                    self._logger.warning(
                        "mjpeg_client_stall_timeout idle_ms=%s timeout_ms=%s path=%s",
                        int(idle_s * 1000),
                        int(self._stall_timeout_s * 1000),
                        self._path,
                    )
                    await self.close("client_stall_timeout")
                    return
        except asyncio.CancelledError:
            return


async def build_camera_mjpeg_stream(
    request: Request,
    *,
    image_format: str,
    quality: int,
    limit_detail: str,
    timeout_log_message: str,
    logger: logging.Logger,
) -> StreamingResponse:
    """构建 MJPEG 流响应 / Build MJPEG stream response."""
    limiter = get_mjpeg_stream_limiter()
    lease = await limiter.try_acquire()
    if lease is None:
        path = str(getattr(getattr(request, "url", None), "path", "") or "")
        logger.warning(
            "mjpeg_try_acquire_rejected active=%s max=%s path=%s",
            limiter.active_clients,
            limiter.max_clients,
            path,
        )
        raise HTTPException(status_code=503, detail=limit_detail)

    boundary = "frame"
    settings = get_settings()
    fetch_timeout_s = settings.stream_mjpeg_frame_fetch_timeout_ms / 1000.0
    configured_stall_timeout_ms = settings.stream_mjpeg_client_stall_timeout_ms
    stall_timeout_s = (
        max(
            configured_stall_timeout_ms,
            settings.stream_mjpeg_frame_fetch_timeout_ms + 5000,
        )
        / 1000.0
        if configured_stall_timeout_ms > 0
        else 0.0
    )
    content_type = "image/jpeg" if image_format.lower() == "jpeg" else "image/png"
    path = str(getattr(getattr(request, "url", None), "path", "") or "")
    manager = get_camera_manager()
    session = _MjpegStreamSession(
        lease=lease,
        manager=manager,
        stall_timeout_s=stall_timeout_s,
        logger=logger,
        path=path,
    )
    session.start_watchdog()

    async def frame_generator():
        release_reason = "response_complete"
        try:
            if not await session.acquire_preview_consumer():
                return
            last_snap_frame_id = -1
            last_emit_mono = 0.0
            while not session.closed:
                if await request.is_disconnected():
                    release_reason = "client_disconnect"
                    break
                try:
                    code, data, snap_id = await asyncio.wait_for(
                        camera_domain_service.get_stream_frame_bytes(
                            image_format, quality, since_frame_id=last_snap_frame_id
                        ),
                        timeout=fetch_timeout_s,
                    )
                except asyncio.TimeoutError:
                    release_reason = "frame_fetch_timeout"
                    logger.warning(timeout_log_message)
                    break
                if code == 304:
                    if not await mjpeg_sleep_or_disconnect(request, 0.03):
                        release_reason = "client_disconnect"
                        break
                    continue
                if code != 200 or data is None:
                    if not await mjpeg_sleep_or_disconnect(request, 0.05):
                        release_reason = "client_disconnect"
                        break
                    continue
                now = time.monotonic()
                min_emit_interval = 1.0 / max(1, manager.preview_target_fps)
                wait = last_emit_mono + min_emit_interval - now
                if wait > 0 and not await mjpeg_sleep_or_disconnect(request, wait):
                    release_reason = "client_disconnect"
                    break
                last_snap_frame_id = snap_id
                last_emit_mono = time.monotonic()
                yield (
                    b"--"
                    + boundary.encode()
                    + b"\r\n"
                    + b"Content-Type: "
                    + content_type.encode()
                    + b"\r\n"
                    + b"Content-Length: "
                    + str(len(data)).encode()
                    + b"\r\n\r\n"
                    + data
                    + b"\r\n"
                )
                await session.touch()
        except asyncio.CancelledError:
            release_reason = "cancelled"
            raise
        except GeneratorExit:
            release_reason = "generator_closed"
            raise
        except Exception:
            release_reason = "stream_error"
            raise
        finally:
            await session.close(release_reason)

    return StreamingResponse(
        frame_generator(),
        media_type=f"multipart/x-mixed-replace; boundary={boundary}",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "X-Accel-Buffering": "no",
        },
        background=BackgroundTask(session.close, "response_complete"),
    )
