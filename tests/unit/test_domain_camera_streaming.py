"""MJPEG 流生命周期测试 / MJPEG stream lifecycle tests."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from ogscope.domain.camera import streaming as streaming_mod
from ogscope.domain.camera.stream_limiter import MjpegStreamLimiter


class _FakeRequest:
    def __init__(self, disconnect_states: list[bool]) -> None:
        self._states = disconnect_states
        self._idx = 0

    async def is_disconnected(self) -> bool:
        if self._idx >= len(self._states):
            return self._states[-1]
        value = self._states[self._idx]
        self._idx += 1
        return value


class _FakeSettings:
    stream_mjpeg_frame_fetch_timeout_ms = 1000
    stream_mjpeg_client_stall_timeout_ms = 1000


class _FakeManager:
    def __init__(self) -> None:
        self.acquired = False
        self.released = False
        self.preview_target_fps = 8

    async def acquire_preview_consumer(self) -> None:
        self.acquired = True

    async def release_preview_consumer(self) -> None:
        self.released = True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_camera_mjpeg_stream_rejects_when_limit_reached(
    monkeypatch,
) -> None:
    limiter = MjpegStreamLimiter(1)
    held_lease = await limiter.try_acquire()
    assert held_lease is not None
    monkeypatch.setattr(streaming_mod, "get_mjpeg_stream_limiter", lambda: limiter)

    req = _FakeRequest([False])
    with pytest.raises(HTTPException) as exc:
        await streaming_mod.build_camera_mjpeg_stream(
            req,
            image_format="jpeg",
            quality=75,
            limit_detail="limit",
            timeout_log_message="timeout",
            logger=streaming_mod.logging.getLogger(__name__),
        )
    assert exc.value.status_code == 503
    await held_lease.release()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_camera_mjpeg_stream_yields_frame_and_releases(monkeypatch) -> None:
    limiter = MjpegStreamLimiter(2)
    monkeypatch.setattr(streaming_mod, "get_mjpeg_stream_limiter", lambda: limiter)
    monkeypatch.setattr(streaming_mod, "get_settings", lambda: _FakeSettings())

    manager = _FakeManager()
    monkeypatch.setattr(streaming_mod, "get_camera_manager", lambda: manager)

    async def _fake_get_stream_frame_bytes(
        fmt: str, quality: int, *, since_frame_id: int
    ):
        _ = fmt, quality, since_frame_id
        return 200, b"abc", 1

    monkeypatch.setattr(
        streaming_mod.camera_domain_service,
        "get_stream_frame_bytes",
        _fake_get_stream_frame_bytes,
    )

    resp = await streaming_mod.build_camera_mjpeg_stream(
        _FakeRequest([False, True]),
        image_format="jpeg",
        quality=75,
        limit_detail="limit",
        timeout_log_message="timeout",
        logger=streaming_mod.logging.getLogger(__name__),
    )
    body_iter = resp.body_iterator
    first_chunk = await anext(body_iter)
    assert b"Content-Type: image/jpeg" in first_chunk
    await body_iter.aclose()

    assert limiter.active_clients == 0
    assert manager.acquired is True
    assert manager.released is True
    snapshot = await limiter.snapshot()
    assert snapshot["release_reasons"] == {"generator_closed": 1}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_releases_slot_before_slow_camera_cleanup() -> None:
    limiter = MjpegStreamLimiter(1)
    lease = await limiter.try_acquire()
    assert lease is not None
    cleanup_started = asyncio.Event()
    allow_cleanup = asyncio.Event()

    class _SlowReleaseManager(_FakeManager):
        async def release_preview_consumer(self) -> None:
            cleanup_started.set()
            await allow_cleanup.wait()
            self.released = True

    manager = _SlowReleaseManager()
    session = streaming_mod._MjpegStreamSession(
        lease=lease,
        manager=manager,
        stall_timeout_s=0,
        logger=streaming_mod.logging.getLogger(__name__),
        path="/test",
    )
    assert await session.acquire_preview_consumer() is True

    close_caller = asyncio.create_task(session.close("cancelled"))
    await cleanup_started.wait()
    assert limiter.active_clients == 0
    close_caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await close_caller

    allow_cleanup.set()
    for _ in range(20):
        if manager.released:
            break
        await asyncio.sleep(0.01)
    assert manager.released is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_watchdog_reclaims_stalled_client() -> None:
    limiter = MjpegStreamLimiter(1)
    lease = await limiter.try_acquire()
    assert lease is not None
    manager = _FakeManager()
    session = streaming_mod._MjpegStreamSession(
        lease=lease,
        manager=manager,
        stall_timeout_s=0.05,
        logger=streaming_mod.logging.getLogger(__name__),
        path="/test",
    )
    assert await session.acquire_preview_consumer() is True
    session.start_watchdog()

    for _ in range(30):
        if limiter.active_clients == 0 and manager.released:
            break
        await asyncio.sleep(0.01)

    assert limiter.active_clients == 0
    assert manager.released is True
    snapshot = await limiter.snapshot()
    assert snapshot["stalled_clients_total"] == 1
    await session.close("duplicate")
