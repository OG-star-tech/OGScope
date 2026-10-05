"""Analysis capture ownership regressions / 分析相机生命周期回归测试。"""

import asyncio

import numpy as np
import pytest

from ogscope.core.realtime import service as service_module
from ogscope.core.realtime.service import RealtimeSolveService
from ogscope.web.camera_shared import CameraManager


class FrameCamera:
    """Small camera with observable capture state / 可观察采集状态的小型相机。"""

    is_initialized = True
    is_capturing = False

    def start_capture(self):
        self.is_capturing = True
        return True

    def stop_capture(self):
        self.is_capturing = False
        return True

    def get_video_frame(self):
        return np.zeros((32, 32, 3), dtype=np.uint8)

    def get_camera_info(self):
        return {}


@pytest.mark.asyncio
async def test_analysis_reopens_idle_camera_and_holds_it_until_cancellation(
    monkeypatch,
):
    """分析自动重开相机并跨越空闲预算持有 / Reopen capture and retain it beyond the idle budget."""
    manager = CameraManager()
    manager._idle_shutdown_sec = 0.01
    camera = FrameCamera()
    manager.attach_camera_instance(camera)
    entered = asyncio.Event()

    async def wait_for_stop(*_):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(service_module, "get_camera_manager", lambda: manager)
    service = RealtimeSolveService()
    monkeypatch.setattr(service, "_run_loop", wait_for_stop)
    await service.start()
    await asyncio.wait_for(entered.wait(), timeout=1)
    assert camera.is_capturing
    manager._schedule_idle_shutdown()
    await asyncio.sleep(0.04)
    assert camera.is_capturing
    assert manager._analysis_consumers == 1
    await service.stop()
    await asyncio.sleep(0.04)
    assert manager._analysis_consumers == 0
    assert not camera.is_capturing
    assert manager.get_camera_instance() is None


@pytest.mark.asyncio
async def test_camera_start_failure_ends_analysis_with_an_error(monkeypatch):
    """启动失败不能永久显示运行中 / A capture startup failure cannot stay running forever."""
    manager = CameraManager()
    manager._idle_shutdown_sec = 0

    async def fail_start():
        raise RuntimeError("camera offline")

    monkeypatch.setattr(manager, "ensure_started", fail_start)
    monkeypatch.setattr(service_module, "get_camera_manager", lambda: manager)
    service = RealtimeSolveService()
    await service.start()
    await service._task
    assert service.state.running is False
    assert service.state.last_error == "camera offline"
    assert manager._analysis_consumers == 0


@pytest.mark.asyncio
async def test_cancelling_during_camera_start_does_not_leak_a_consumer(monkeypatch):
    """启动中取消不能遗留持有者 / Cancellation during startup cannot leak a capture owner."""
    manager = CameraManager()
    manager._idle_shutdown_sec = 0
    entered = asyncio.Event()

    async def pending_start():
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(manager, "ensure_started", pending_start)
    monkeypatch.setattr(service_module, "get_camera_manager", lambda: manager)
    service = RealtimeSolveService()
    await service.start()
    await asyncio.wait_for(entered.wait(), timeout=1)
    await service.stop()
    assert manager._analysis_consumers == 0
