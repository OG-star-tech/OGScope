"""CameraManager 帧健康与离线判定单元测试 / CameraManager frame health unit tests."""

from __future__ import annotations

import asyncio

import numpy as np
import pytest

from ogscope.web.camera_shared import CameraManager


class _NoFrameCamera:
    is_initialized = True
    is_capturing = False

    def start_capture(self) -> bool:
        self.is_capturing = True
        return True

    def stop_capture(self) -> bool:
        self.is_capturing = False
        return True

    def get_camera_info(self) -> dict:
        return {"sensor": "test"}

    def get_video_frame(self):
        return None


class _FrameCamera(_NoFrameCamera):
    def __init__(self) -> None:
        self.read_count = 0

    def get_video_frame(self):
        self.read_count += 1
        return np.zeros((360, 640, 3), dtype=np.uint8)


@pytest.mark.asyncio
async def test_ensure_started_fails_when_no_frames() -> None:
    manager = CameraManager()
    manager._probe_timeout_sec = 0.2
    manager.attach_camera_instance(_NoFrameCamera())

    with pytest.raises(RuntimeError, match="无有效帧|no frames"):
        await manager.ensure_started()

    status = await manager.status()
    assert status["connected"] is False
    assert status["streaming"] is False
    assert status.get("error")


@pytest.mark.asyncio
async def test_ensure_started_succeeds_when_frames_available() -> None:
    manager = CameraManager()
    manager._probe_timeout_sec = 0.5
    manager.attach_camera_instance(_FrameCamera())

    await manager.ensure_started()
    status = await manager.status()
    assert status["connected"] is True
    assert status["streaming"] is True

    await manager.stop()


@pytest.mark.asyncio
async def test_ensure_started_fast_path_does_not_probe_again() -> None:
    """新鲜相机重复ensure不应额外抓帧 / Fresh repeated ensure must not grab another frame."""
    manager = CameraManager()
    camera = _FrameCamera()
    manager.attach_camera_instance(camera)

    await manager.ensure_started()
    first_reads = camera.read_count
    await manager.ensure_started()

    assert first_reads == 1
    assert camera.read_count == first_reads
    await manager.stop()


@pytest.mark.asyncio
async def test_preview_consumer_stops_grabber_on_last_release() -> None:
    """最后一个预览消费者离开后停止编码任务 / Stop encoding after the last preview consumer."""
    manager = CameraManager()
    manager._idle_shutdown_sec = 60
    manager.attach_camera_instance(_FrameCamera())

    await manager.acquire_preview_consumer()
    await asyncio.sleep(0.03)
    await manager.release_preview_consumer()

    metrics = await manager.stream_metrics()
    assert metrics["preview_consumers"] == 0
    assert manager._grabber_task is None
    await manager.stop()


def test_preview_fps_is_independent_runtime_setting() -> None:
    manager = CameraManager()
    assert manager.set_preview_fps(12) == 12
    assert manager._target_fps == 12
