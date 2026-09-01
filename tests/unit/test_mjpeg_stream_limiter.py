"""MJPEG 会话限制单元测试 / Unit tests for MJPEG stream session limiter."""

from __future__ import annotations

import asyncio

import pytest

from ogscope.web.mjpeg_stream_limiter import MjpegStreamLimiter


@pytest.mark.asyncio
async def test_limiter_unlimited_tracks_and_releases_leases() -> None:
    lim = MjpegStreamLimiter(0)
    first = await lim.try_acquire()
    second = await lim.try_acquire()
    assert first is not None
    assert second is not None
    assert lim.active_clients == 2

    assert await first.release("client_disconnect") is True
    assert await first.release("duplicate") is False
    assert await second.release("response_complete") is True
    assert lim.active_clients == 0

    snapshot = await lim.snapshot()
    assert snapshot["released_clients_total"] == 2
    assert snapshot["release_reasons"] == {
        "client_disconnect": 1,
        "response_complete": 1,
    }


@pytest.mark.asyncio
async def test_limiter_one_client_blocks_second_until_lease_release() -> None:
    lim = MjpegStreamLimiter(1)
    lease = await lim.try_acquire()
    assert lease is not None
    assert await lim.try_acquire() is None
    assert await lease.release() is True
    replacement = await lim.try_acquire()
    assert replacement is not None
    await replacement.release()


@pytest.mark.asyncio
async def test_limiter_touch_updates_idle_metric() -> None:
    lim = MjpegStreamLimiter(1)
    lease = await lim.try_acquire()
    assert lease is not None
    await asyncio.sleep(0.02)
    before = await lim.snapshot()
    assert before["oldest_client_idle_ms"] >= 10

    assert await lease.touch() is True
    after = await lim.snapshot()
    assert after["oldest_client_idle_ms"] < before["oldest_client_idle_ms"]
    await lease.release("client_stall_timeout")
    final = await lim.snapshot()
    assert final["stalled_clients_total"] == 1
