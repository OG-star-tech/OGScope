"""CameraManager 帧健康与离线判定单元测试 / CameraManager frame health unit tests."""

from __future__ import annotations

import asyncio
import threading
import time
from unittest.mock import AsyncMock

import numpy as np
import pytest

from ogscope.web.camera_shared import CameraManager


@pytest.mark.asyncio
async def test_preview_rechecks_camera_after_queued_close_takes_control(monkeypatch):
    """锁已释放但关闭仍在排队时，预览必须重查句柄 / Recheck after a queued closer wins the lock."""
    queued = asyncio.Event()

    class ObservedLock(asyncio.Lock):
        async def acquire(self):
            if self.locked():
                queued.set()
            return await super().acquire()

    manager = CameraManager()
    manager._control_lock = ObservedLock()
    first, second = _FrameCamera(), _FrameCamera()
    first.camera = _CloseProbe()
    manager.attach_camera_instance(first)
    monkeypatch.setattr(manager, "_create_camera_sync", lambda: second)
    monkeypatch.setattr(manager, "_ensure_grabber_locked", AsyncMock())
    try:
        await manager.ensure_started()
        await manager._control_lock.acquire()
        closing = asyncio.create_task(manager.stop())
        await asyncio.wait_for(queued.wait(), 1)
        manager._control_lock.release()
        # 不让出事件循环，复现 unlocked 但已有锁等待者的窗口。
        # Keep the event-loop turn: the lock is unlocked but already has a waiter.
        await manager.acquire_preview_consumer()
        await closing
        assert first.camera.closed
        assert manager.get_camera_instance() is second
        assert (await manager.status())["streaming"] is True
    finally:
        await manager.release_preview_consumer()
        await manager.stop(force=True)
        manager._capture_executor.shutdown(wait=True)
        manager._jpeg_executor.shutdown(wait=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["stop", "close"])
async def test_cancelled_close_quarantines_handle_until_native_worker_finishes(
    monkeypatch, operation
):
    """取消等待不等于取消原生关闭 / Cancelling the waiter cannot cancel native closure."""
    manager = CameraManager()
    camera = _FrameCamera()
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()

    def blocked():
        entered.set()
        try:
            release.wait(timeout=3)
            camera.is_capturing = False
            return True
        finally:
            finished.set()

    monkeypatch.setattr(
        camera,
        "stop_capture" if operation == "stop" else "close",
        blocked,
        raising=False,
    )
    manager.attach_camera_instance(camera)
    try:
        await manager.ensure_started()
        closing = asyncio.create_task(manager.stop())
        assert await asyncio.to_thread(entered.wait, 1)
        arriving = asyncio.create_task(manager.acquire_analysis_consumer())
        await asyncio.sleep(0)
        assert not arriving.done()
        closing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await closing
        assert manager.get_camera_instance() is camera
        assert (await manager.status())["restart_required"] is True
        with pytest.raises(RuntimeError, match="restart required|重启服务"):
            await arriving
        assert manager.lifecycle_status()["analysis_consumers"] == 0
    finally:
        release.set()
        await asyncio.to_thread(finished.wait, 1)
        await manager.stop(force=True)
        manager._capture_executor.shutdown(wait=True)
        manager._jpeg_executor.shutdown(wait=True)


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


class _FailedStopCamera(_FrameCamera):
    """模拟驱动报告无法释放 / Simulate a driver reporting release failure."""

    is_capturing = True

    def stop_capture(self) -> bool:
        return False


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
async def test_startup_allows_long_mode_transition_before_first_analysis_frame(
    monkeypatch,
) -> None:
    """3 秒模式切换不能被旧 2 秒探测预算误杀 / A 3s transition must outlive the old 2s startup probe."""
    clock = [0.0]
    monkeypatch.setattr("ogscope.web.camera_shared.time.time", lambda: clock[0])
    monkeypatch.setattr("ogscope.web.camera_shared.time.sleep", lambda _seconds: None)

    class LongCamera(_FrameCamera):
        capture_timeout_sec = 8.0

        def get_video_frame(self):
            clock[0] += 3.0
            self.read_count += 1
            if self.read_count == 1:
                return None
            return np.zeros((360, 640, 3), dtype=np.uint8)

    manager = CameraManager()
    manager._probe_timeout_sec = 2.0
    camera = LongCamera()
    manager.attach_camera_instance(camera)
    await manager.ensure_started()
    assert camera.read_count == 2
    assert (await manager.status())["connected"] is True
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


def test_lifecycle_stop_budget_outlives_long_exposure_capture() -> None:
    """停止预算必须覆盖长曝光抓帧收敛 / Stop budget must outlive long-AE capture."""
    manager = CameraManager()

    assert manager._capture_timeout_sec >= 8.0
    assert manager._stop_timeout_sec >= manager._capture_timeout_sec + 2.0


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
async def test_stop_failure_keeps_camera_handle_and_requires_restart() -> None:
    """显式停止失败不得被后续 close 掩盖 / A stop failure must not be hidden by close."""
    manager = CameraManager()
    camera = _FailedStopCamera()
    manager.attach_camera_instance(camera)

    await manager.stop()

    assert manager.get_camera_instance() is camera
    assert manager._restart_required is True


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


@pytest.mark.asyncio
async def test_failed_start_closes_old_handle_before_a_successful_retry(monkeypatch):
    """已安全关闭的启动失败允许重新创建 / Retry a failed start only after safe release."""
    manager = CameraManager()
    first, second = _FrameCamera(), _FrameCamera()
    first.camera = _CloseProbe()
    monkeypatch.setattr(first, "start_capture", lambda: False)
    cameras = iter([first, second])
    monkeypatch.setattr(manager, "_create_camera_sync", lambda: next(cameras))
    try:
        with pytest.raises(RuntimeError, match="启动失败|start failed"):
            await manager.ensure_started()
        assert first.camera.closed
        assert manager.get_camera_instance() is None
        await manager.ensure_started()
        assert manager.get_camera_instance() is second
        assert (await manager.status())["streaming"] is True
    finally:
        await manager.stop(force=True)
        manager._capture_executor.shutdown(wait=True)
        manager._jpeg_executor.shutdown(wait=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("idle", [True, False])
async def test_new_analysis_waits_for_inflight_close(monkeypatch, idle):
    """新消费者不能中断正在释放的硬件 / New consumers must let hardware release finish."""
    manager = CameraManager()
    first, second = _FrameCamera(), _FrameCamera()
    first.camera = _CloseProbe()
    entered, release = threading.Event(), threading.Event()

    def slow_stop():
        entered.set()
        release.wait(timeout=2)
        first.is_capturing = False
        return True

    monkeypatch.setattr(first, "stop_capture", slow_stop)
    monkeypatch.setattr(manager, "_create_camera_sync", lambda: second)
    manager.attach_camera_instance(first)
    manager._idle_shutdown_sec = 0 if idle else 60
    consumer = None
    try:
        await manager.ensure_started()
        closing = (
            manager._idle_shutdown_task if idle else asyncio.create_task(manager.stop())
        )
        assert await asyncio.to_thread(entered.wait, 1)
        consumer = asyncio.create_task(manager.acquire_analysis_consumer())
        await asyncio.sleep(0)
        release.set()
        await asyncio.wait_for(consumer, 2)
        await asyncio.wait_for(closing, 2)
        assert first.camera.closed
        assert manager.get_camera_instance() is second
        assert manager.lifecycle_status()["analysis_consumers"] == 1
        assert (await manager.status())["streaming"] is True
    finally:
        release.set()
        if consumer:
            await asyncio.gather(consumer, return_exceptions=True)
        await manager.release_analysis_consumer()
        await manager.stop(force=True)
        manager._capture_executor.shutdown(wait=True)
        manager._jpeg_executor.shutdown(wait=True)
