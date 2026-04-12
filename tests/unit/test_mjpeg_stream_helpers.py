"""mjpeg_stream_helpers 单元测试 / Unit tests for mjpeg_stream_helpers."""

from __future__ import annotations

import pytest

from ogscope.web.mjpeg_stream_helpers import mjpeg_sleep_or_disconnect


class _DummyRequest:
    """仅实现 is_disconnected，用于单元测试 / Minimal request stub for unit tests."""

    def __init__(self, disconnect_on_call: int | None = None) -> None:
        self._n = 0
        self._disconnect_on = disconnect_on_call

    async def is_disconnected(self) -> bool:
        self._n += 1
        if self._disconnect_on is None:
            return False
        return self._n >= self._disconnect_on


@pytest.mark.asyncio
async def test_mjpeg_sleep_zero_returns_not_disconnected() -> None:
    req = _DummyRequest(disconnect_on_call=None)
    ok = await mjpeg_sleep_or_disconnect(req, 0.0)
    assert ok is True
    assert req._n == 1


@pytest.mark.asyncio
async def test_mjpeg_sleep_sees_disconnect_during_chunked_wait() -> None:
    req = _DummyRequest(disconnect_on_call=4)
    ok = await mjpeg_sleep_or_disconnect(req, 0.2, chunk_s=0.02)
    assert ok is False
    assert req._n >= 4
