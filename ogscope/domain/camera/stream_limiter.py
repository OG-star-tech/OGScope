"""
MJPEG 长连接并发限制 / Concurrent MJPEG stream limiter
"""

from __future__ import annotations

import asyncio

from ogscope.config import get_settings


class MjpegStreamLimiter:
    """限制同时活跃的 MJPEG 响应数，减轻低配板内存与 WiFi 压力 / Cap concurrent MJPEG responses."""

    def __init__(self, max_clients: int) -> None:
        self._max = max(0, int(max_clients))
        self._count = 0
        self._lock = asyncio.Lock()

    @property
    def max_clients(self) -> int:
        return self._max

    @property
    def active_clients(self) -> int:
        return self._count

    async def try_acquire(self) -> bool:
        """若未超限则占用一个名额并返回 True / Acquire one slot if under limit."""
        if self._max <= 0:
            return True
        async with self._lock:
            if self._count >= self._max:
                return False
            self._count += 1
            return True

    async def release(self) -> None:
        """释放一个名额（与 try_acquire 成对）/ Release one slot."""
        if self._max <= 0:
            return
        async with self._lock:
            self._count = max(0, self._count - 1)


_limiter: MjpegStreamLimiter | None = None


def get_mjpeg_stream_limiter() -> MjpegStreamLimiter:
    """单例，配置来自 Settings / Singleton from app settings."""
    global _limiter
    if _limiter is None:
        _limiter = MjpegStreamLimiter(get_settings().stream_max_mjpeg_clients)
    return _limiter

