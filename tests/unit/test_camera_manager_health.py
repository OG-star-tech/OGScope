"""CameraManager 帧健康与离线判定单元测试 / CameraManager frame health unit tests."""

from __future__ import annotations

import asyncio
import time

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


class _CloseProbe:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _SlowStopCamera(_FrameCamera):
    """模拟底层 stop 暂时卡住 / Simulate a temporarily stuck low-level stop."""

    def __init__(self) -> None:
        super().__init__()
        self.camera = _CloseProbe()
        self.is_capturing = True

    def stop_capture(self) -> bool:
        time.sleep(0.08)
        self.is_capturing = False
        return True


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
async def test_status_uses_successful_raw_probe_without_jpeg_grabber() -> None:
    """冷启动探测帧应直接建立流健康状态 / Cold-start raw probe must establish stream health."""
    manager = CameraManager()
    manager._probe_timeout_sec = 0.5
    camera = _FrameCamera()
    manager.attach_camera_instance(camera)

    await manager.ensure_started()
    assert manager._frame_id == 0

    status = await manager.status()
    assert status["connected"] is True
    assert status["streaming"] is True
    await manager.stop()


@pytest.mark.asyncio
async def test_stale_camera_reprobe_restores_status_without_jpeg_grabber() -> None:
    """过期采集重新探测后应一次恢复 / A stale capture should recover after one re-probe."""
    manager = CameraManager()
    manager._probe_timeout_sec = 0.5
    manager._stale_timeout_sec = 0.5
    camera = _FrameCamera()
    manager.attach_camera_instance(camera)

    await manager.ensure_started()
    manager._last_capture_success_mono -= 2.0

    idle_status = await manager.status()
    assert idle_status["connected"] is True
    assert idle_status["streaming"] is True

    await manager.ensure_started()

    status = await manager.status()
    assert camera.read_count == 2
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


@pytest.mark.asyncio
async def test_stop_timeout_keeps_camera_handle_and_blocks_reacquire() -> None:
    """stop 超时后不得丢弃仍占用 libcamera 的实例 / Keep the handle after stop timeout."""
    manager = CameraManager()
    camera = _SlowStopCamera()
    manager.attach_camera_instance(camera)
    manager._stop_timeout_sec = 0.01

    await manager.stop()

    assert manager.get_camera_instance() is camera
    status = await manager.status()
    assert status["connected"] is False
    assert status["restart_required"] is True
    with pytest.raises(RuntimeError, match="restart required|重启服务"):
        await manager.ensure_started()

    # 让首次 stop 工作线程收尾，再确认一次显式 stop 可以安全释放。
    # Let the first stop worker drain, then verify an explicit retry can release safely.
    await asyncio.sleep(0.1)
    manager._stop_timeout_sec = 0.2
    await manager.stop()
    assert manager.get_camera_instance() is None
    assert camera.camera.closed is True


@pytest.mark.asyncio
async def test_reconfigure_timeout_marks_restart_required_and_stops_grabber() -> None:
    """重配置超时后不得恢复抓帧 / Do not resume the grabber after reconfigure timeout."""
    manager = CameraManager()
    camera = _FrameCamera()
    manager.attach_camera_instance(camera)
    camera.is_capturing = True

    def _slow_reconfigure() -> bool:
        time.sleep(0.08)
        return True

    with pytest.raises(asyncio.TimeoutError):
        await manager.reconfigure_camera(
            "slow_test", _slow_reconfigure, timeout_sec=0.01
        )

    assert manager._restart_required is True
    assert manager._grabber_task is None
    await asyncio.sleep(0.1)
