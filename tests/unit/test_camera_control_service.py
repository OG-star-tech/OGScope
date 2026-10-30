"""共享控制迁移的行为保护 / Behavioral protection for shared control migration."""

import asyncio
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from ogscope.application import camera as composition
from ogscope.application.camera_control import CameraControlService
from ogscope.domain.camera.runtime import CameraRuntime, SharedFrame
from ogscope.domain.camera.services import CameraDomainService


class Sensor:
    """记录可恢复的相机参数，不接触设备 / Track restorable controls without a device."""

    def __init__(self):
        self.is_initialized = True
        self.is_capturing = True
        self.auto_exposure = True
        self.exposure_us = 12345
        self.analogue_gain = 2.0
        self.digital_gain = 1.5
        self.noise_reduction_mode = "temporal"
        self.fps = 8

    def get_camera_info(self):
        return {"fps": self.fps, "actual_exposure_us": self.exposure_us}

    def set_auto_exposure(self, enabled):
        self.auto_exposure = enabled
        return True

    def set_exposure(self, exposure):
        self.exposure_us = exposure
        return True

    def set_gain(self, analogue, digital=1.0):
        self.analogue_gain, self.digital_gain = analogue, digital
        return True

    def set_noise_reduction_mode(self, mode):
        self.noise_reduction_mode = mode
        return True

    def set_fps(self, fps):
        self.fps = fps
        return True


def make_control(*, analysis_running=False):
    """按实例组合传感器、占用和覆盖参数 / Compose sensor, ownership and overrides per instance."""
    sensor, overrides = Sensor(), {}
    ownership = {
        "analysis_consumers": 0,
        "operation_consumers": 0,
        "recording_consumers": 0,
    }

    async def reconfigure(name, fn, *, timeout_sec):
        return fn()

    async def status():
        return {
            "connected": True,
            "streaming": sensor.is_capturing,
            "info": sensor.get_camera_info(),
            "runtime_overrides": dict(overrides),
            "configured_backend": "v4l2",
        }

    capture = SimpleNamespace(
        get_camera_instance=Mock(return_value=sensor),
        lifecycle_status=Mock(return_value=ownership),
        ensure_started=AsyncMock(),
        stop=AsyncMock(),
        status=status,
        reconfigure_camera=AsyncMock(side_effect=reconfigure),
        get_runtime_overrides=lambda: dict(overrides),
        update_runtime_overrides=overrides.update,
        clear_runtime_overrides=overrides.clear,
        get_preview_frame=AsyncMock(return_value=(503, None)),
    )
    return CameraControlService(capture, analysis_running=lambda: analysis_running)


def test_default_controls_run_without_loading_web_debug_or_http():
    """禁止旧调试模块后仍能组合和启停 / Compose and control while legacy debug imports are forbidden."""
    subprocess.run(
        [
            sys.executable,
            "-c",
            """
import asyncio
import importlib.abc
import sys
from unittest.mock import AsyncMock

class RejectDebug(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname.startswith(('ogscope.web', 'fastapi', 'starlette')):
            raise AssertionError(fullname)

sys.meta_path.insert(0, RejectDebug())
from ogscope.application.camera import get_camera_runtime
runtime = get_camera_runtime()
assert runtime.control.capture is runtime.capture
runtime.capture.ensure_started = AsyncMock()
runtime.capture.stop = AsyncMock()

async def exercise():
    assert (await runtime.control.get_camera_status())['connected'] is False
    assert (await runtime.control.start_camera())['success'] is True
    assert (await runtime.control.stop_camera())['success'] is True

asyncio.run(exercise())
assert not any(name.startswith('ogscope.web') for name in sys.modules)
""",
        ],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "owner",
    [
        "analysis_consumers",
        "operation_consumers",
        "recording_consumers",
        "analysis_starting",
    ],
)
async def test_busy_stop_does_not_reach_capture(owner):
    """分析启动窗口及各类占用仍阻止停机 / Keep startup and ownership stop guards."""
    control = make_control(analysis_running=owner == "analysis_starting")
    if owner != "analysis_starting":
        control.capture.lifecycle_status.return_value[owner] = 1
    result = await control.stop_camera()
    assert result["success"] is False
    control.capture.stop.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_and_stop_failures_are_not_reported_as_success():
    """失败不转成成功回执，也不重新取得句柄 / Preserve failure receipts without reacquiring a handle."""
    control = make_control()
    control.capture.ensure_started.side_effect = RuntimeError("start failed")
    with pytest.raises(RuntimeError, match="start failed"):
        await control.start_camera()
    control.capture.stop.side_effect = RuntimeError("restart required")
    assert await control.stop_camera() == {
        "success": False,
        "message": "restart required",
    }
    assert control.capture.ensure_started.await_count == 1


@pytest.mark.asyncio
async def test_reconfiguration_timeout_does_not_publish_unapplied_overrides():
    """重配超时不能写入成功参数 / Reconfiguration timeout must not publish successful overrides."""
    control = make_control()
    control.capture.update_runtime_overrides({"fps": 8})
    control.capture.reconfigure_camera.side_effect = asyncio.TimeoutError()
    with pytest.raises(Exception, match="设置帧率失败"):
        await control.set_fps(12)
    assert control.capture.get_runtime_overrides() == {"fps": 8}
    assert control.get_camera_instance().fps == 8
    assert control.capture.reconfigure_camera.await_args.kwargs["timeout_sec"] == 10.0


@pytest.mark.asyncio
async def test_fps_fallback_and_single_readback_retry_keep_budget():
    """旧驱动仍通过分辨率接口设置帧率并仅重试一次 / Preserve old-driver FPS fallback and one retry."""
    control = make_control()
    info = {"width": 640, "height": 360, "fps": 8}
    calls = []

    def set_resolution(width, height, fps):
        calls.append((width, height, fps))
        if len(calls) == 2:
            info["fps"] = fps
        return True

    sensor = SimpleNamespace(
        is_initialized=True,
        get_camera_info=lambda: dict(info),
        set_resolution=set_resolution,
    )
    control.capture.get_camera_instance.return_value = sensor
    assert (await control.set_fps(12))["info"]["fps"] == 12
    assert calls == [(640, 360, 12), (640, 360, 12)]
    assert [
        call.kwargs["timeout_sec"]
        for call in control.capture.reconfigure_camera.await_args_list
    ] == [10.0, 10.0]
    assert control.capture.get_runtime_overrides() == {"fps": 12}


@pytest.mark.asyncio
async def test_focus_and_recording_state_are_isolated_and_stop_restores_controls():
    """调焦/录像状态互不串扰，停机保留恢复顺序 / Isolate control state and preserve focus restoration on stop."""
    first, second = make_control(), make_control()
    first.capture.update_runtime_overrides({"fps": 8})
    first.recording = True
    await first.start_focus_session()
    assert first.get_camera_instance().auto_exposure is False
    assert second.get_camera_instance().auto_exposure is True
    assert (await first.get_camera_status())["recording"] is True
    assert (await second.get_camera_status())["recording"] is False
    assert (await second.stop_focus_session())["restored"] is False
    first.recording = False
    assert (await first.stop_camera())["success"] is True
    sensor = first.get_camera_instance()
    assert (
        sensor.auto_exposure,
        sensor.exposure_us,
        sensor.analogue_gain,
        sensor.digital_gain,
        sensor.noise_reduction_mode,
    ) == (True, 12345, 2.0, 1.5, "temporal")
    assert first.capture.get_runtime_overrides() == {"fps": 8}
    first.capture.stop.assert_awaited_once()
    second.capture.stop.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_focus_restore_keeps_snapshot_for_retry():
    """恢复失败保留快照且不停止设备 / Failed restoration retains its snapshot and does not stop capture."""
    control = make_control()
    await control.start_focus_session()
    control.capture.reconfigure_camera.side_effect = RuntimeError("reconfigure failed")
    with pytest.raises(Exception, match="reconfigure failed"):
        await control.stop_camera()
    control.capture.stop.assert_not_awaited()
    assert (await control.start_focus_session())["already_active"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [200, 304, 503])
async def test_preview_frame_http_contract_and_legacy_entry_match(monkeypatch, code):
    """帧值迁出后保留响应码、身份头及旧入口 / Preserve status, identity headers and legacy preview entry."""
    from ogscope.web.api.debug.services import DebugCameraService

    control = make_control()
    frame = SharedFrame(7, 12.5, None, b"jpeg-bytes", 640, 360)
    control.capture.get_preview_frame.return_value = (
        code,
        frame if code == 200 else None,
    )
    runtime = CameraRuntime(capture=control.capture, control=control)
    monkeypatch.setattr(composition, "_runtime", runtime)
    domain = CameraDomainService(runtime)
    for caller in (domain.get_preview, DebugCameraService.get_preview):
        if code == 503:
            with pytest.raises(HTTPException) as error:
                await caller(since_frame_id=6)
            assert error.value.status_code == 503
        else:
            response = await caller(since_frame_id=6)
            assert response.status_code == code
            if code == 200:
                assert response.body == b"jpeg-bytes"
                assert response.headers["x-frame-id"] == "7"
                assert response.headers["x-frame-ts"] == "12.5"
                assert response.headers["x-frame-width"] == "640"
                assert response.headers["x-frame-height"] == "360"
                assert (
                    response.headers["cache-control"]
                    == "no-cache, no-store, must-revalidate"
                )
