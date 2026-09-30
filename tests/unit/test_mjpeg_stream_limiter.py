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
async def test_limiter_evicts_stalest_session_to_admit_a_new_one_when_full() -> None:
    """名额已满时新连接淘汰最旧的一路而不是被拒绝 / A new connection evicts
    the stalest session instead of being rejected when the slot cap is
    already full - the cap bounds concurrent buffer memory, it should
    never mean turning away a viewer."""
    lim = MjpegStreamLimiter(1)
    first = await lim.try_acquire()
    assert first is not None
    evicted: list[str] = []
    await first.set_evict_callback(lambda: evicted.append("first"))

    second = await lim.try_acquire()

    assert second is not None
    assert evicted == ["first"]
    assert lim.active_clients == 1
    # The evicted lease is already gone from the limiter's bookkeeping.
    assert await first.release("late_release") is False
    assert await second.release() is True
    snapshot = await lim.snapshot()
    assert snapshot["evicted_clients_total"] == 1


@pytest.mark.asyncio
async def test_limiter_eviction_picks_the_stalest_not_just_the_oldest() -> None:
    """按最久未发送进展淘汰，而不是按创建时间 / Eviction picks by longest
    since send progress, not by creation order - a session that's actively
    still sending frames shouldn't be the one dropped just because it
    connected first."""
    lim = MjpegStreamLimiter(2)
    older = await lim.try_acquire()
    newer = await lim.try_acquire()
    assert older is not None and newer is not None
    evicted: list[str] = []
    await older.set_evict_callback(lambda: evicted.append("older"))
    await newer.set_evict_callback(lambda: evicted.append("newer"))

    # The older session keeps actively sending frames; the newer one goes
    # idle without ever making progress.
    await asyncio.sleep(0.01)
    assert await older.touch() is True

    third = await lim.try_acquire()

    assert third is not None
    assert evicted == ["newer"]


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
