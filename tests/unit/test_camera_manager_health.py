"""CameraManager 帧健康与离线判定单元测试 / CameraManager frame health unit tests."""

from __future__ import annotations

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
    def get_video_frame(self):
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
