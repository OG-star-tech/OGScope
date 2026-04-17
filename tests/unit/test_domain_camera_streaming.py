from __future__ import annotations

import pytest
from fastapi import HTTPException

from ogscope.domain.camera import streaming as streaming_mod


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


class _FakeLimiter:
    def __init__(self, can_acquire: bool = True) -> None:
        self.max_clients = 2
        self.active_clients = 0
        self._can_acquire = can_acquire
        self.released = False

    async def try_acquire(self) -> bool:
        return self._can_acquire

    async def release(self) -> None:
        self.released = True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_camera_mjpeg_stream_rejects_when_limit_reached(monkeypatch) -> None:
    limiter = _FakeLimiter(can_acquire=False)
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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_camera_mjpeg_stream_yields_frame_and_releases(monkeypatch) -> None:
    limiter = _FakeLimiter(can_acquire=True)
    monkeypatch.setattr(streaming_mod, "get_mjpeg_stream_limiter", lambda: limiter)

    class _FakeSettings:
        stream_mjpeg_frame_fetch_timeout_ms = 1000

    monkeypatch.setattr(streaming_mod, "get_settings", lambda: _FakeSettings())

    async def _fake_get_stream_frame_bytes(fmt: str, quality: int, *, since_frame_id: int):
        _ = fmt, quality, since_frame_id
        return 200, b"abc", 1

    monkeypatch.setattr(
        streaming_mod.camera_domain_service,
        "get_stream_frame_bytes",
        _fake_get_stream_frame_bytes,
    )

    req = _FakeRequest([False, True])
    resp = await streaming_mod.build_camera_mjpeg_stream(
        req,
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
    assert limiter.released is True

