"""MJPEG 并发限制单元测试 / Unit tests for MJPEG stream limiter."""

from __future__ import annotations

import pytest

from ogscope.web.mjpeg_stream_limiter import MjpegStreamLimiter


@pytest.mark.asyncio
async def test_limiter_unlimited_always_acquires() -> None:
    lim = MjpegStreamLimiter(0)
    assert await lim.try_acquire() is True
    assert await lim.try_acquire() is True
    await lim.release()
    await lim.release()


@pytest.mark.asyncio
async def test_limiter_one_client_blocks_second() -> None:
    lim = MjpegStreamLimiter(1)
    assert await lim.try_acquire() is True
    assert await lim.try_acquire() is False
    await lim.release()
    assert await lim.try_acquire() is True
    await lim.release()


@pytest.mark.asyncio
async def test_limiter_two_clients_blocks_third() -> None:
    lim = MjpegStreamLimiter(2)
    assert await lim.try_acquire() is True
    assert await lim.try_acquire() is True
    assert await lim.try_acquire() is False
    await lim.release()
    assert await lim.try_acquire() is True
    await lim.release()
    await lim.release()
