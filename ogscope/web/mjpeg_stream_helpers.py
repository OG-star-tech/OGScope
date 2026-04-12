"""
MJPEG 长连接辅助：可中断等待与断连检测 / MJPEG streaming helpers: interruptible sleep and disconnect checks
"""

from __future__ import annotations

import asyncio
import time

from starlette.requests import Request


async def mjpeg_sleep_or_disconnect(
    request: Request,
    seconds: float,
    *,
    chunk_s: float = 0.05,
) -> bool:
    """分段 sleep，便于客户端断开后尽快结束生成器并释放名额 / Chunked sleep so disconnect releases the MJPEG slot promptly.

    Returns:
        True 可继续拉流；False 应结束循环（客户端已断开）/ True to continue; False to stop (client gone).
    """
    if seconds <= 0:
        return not await request.is_disconnected()
    deadline = time.monotonic() + float(seconds)
    chunk = max(0.01, float(chunk_s))
    while time.monotonic() < deadline:
        if await request.is_disconnected():
            return False
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        await asyncio.sleep(min(chunk, remaining))
    return not await request.is_disconnected()
