"""RAW cache identity and capture barriers / RAW 缓存身份与采集屏障。"""

import asyncio
import time
from threading import Event
from unittest.mock import AsyncMock

import numpy as np
import pytest

from ogscope.web.camera_shared import CameraManager, CapturedFrame


@pytest.fixture
def manager():
    value = CameraManager()
    value.ensure_started = AsyncMock()
    value._schedule_idle_shutdown = lambda: None
    yield value
    value._capture_executor.shutdown(wait=True)
    value._jpeg_executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_cached_pixels_keep_their_own_sequence_even_after_prefetch(manager):
    pixels = np.ones((4, 6), dtype=np.uint8)
    manager._latest_raw = pixels
    manager._latest_raw_capture = CapturedFrame(pixels, 7, 123.0, time.monotonic(), 0)
    manager._capture_sequence = 9
    frame, identity, timestamp = await manager.get_raw_frame()
    assert identity == 7 and timestamp == 123.0
    assert np.array_equal(frame, pixels) and frame is not pixels


@pytest.mark.asyncio
async def test_warm_idle_cache_is_read_again_instead_of_relabelled(manager):
    pixels = np.ones((4, 6), dtype=np.uint8)
    manager._latest_raw = pixels
    manager._latest_raw_capture = CapturedFrame(
        pixels, 7, 123.0, time.monotonic() - 20, 0
    )
    manager._read_preview_frame_sync = lambda: CapturedFrame(
        pixels * 2, 8, 140.0, time.monotonic(), 0
    )
    frame, identity, timestamp = await manager.get_raw_frame()
    assert identity == 8 and timestamp == 140.0
    assert np.all(frame == 2)


@pytest.mark.asyncio
async def test_direct_read_cannot_be_relabelled_by_a_later_preview(manager):
    pixels = np.ones((4, 6), dtype=np.uint8)

    def read():
        captured = CapturedFrame(pixels, 7, 123.0, time.monotonic(), 0)
        manager._capture_sequence = 8
        return captured

    manager._read_preview_frame_sync = read
    _, identity, timestamp = await manager.get_raw_frame()
    assert identity == 7 and timestamp == 123.0


@pytest.mark.asyncio
async def test_reset_rejects_inflight_read_and_clears_cache_even_without_driver_hook(
    manager,
):
    reading, release = Event(), Event()

    def read():
        epoch = manager._capture_epoch
        reading.set()
        assert release.wait(2)
        return CapturedFrame(np.ones((4, 6)), 1, 123.0, time.monotonic(), epoch)

    manager._read_preview_frame_sync = read
    capture = asyncio.create_task(manager.get_raw_frame())
    assert await asyncio.to_thread(reading.wait, 1)
    reset = asyncio.create_task(manager.reset_temporal_history(object()))
    await asyncio.sleep(0)
    assert manager._reset_pending == 1
    release.set()
    with pytest.raises(RuntimeError, match="No fresh frame"):
        await capture
    assert await reset is False
    assert manager._latest_raw is None and manager._latest_raw_capture is None
    assert manager._reset_pending == 0


@pytest.mark.asyncio
async def test_driver_reset_finishes_before_next_read_and_does_not_keep_raw(manager):
    order = []

    class Camera:
        def begin_fresh_capture_epoch(self):
            order.append("reset")
            return True

    assert await manager.reset_temporal_history(Camera())

    def read():
        order.append("read")
        return CapturedFrame(
            np.ones((4, 6)), 1, 123.0, time.monotonic(), manager._capture_epoch
        )

    manager._read_preview_frame_sync = read
    await manager.get_raw_frame()
    assert order == ["reset", "read"]
    assert manager._latest_raw is None and manager._latest_raw_capture is None
