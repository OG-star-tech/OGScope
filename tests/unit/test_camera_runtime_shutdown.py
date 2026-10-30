"""相机运行服务的终止关闭保护 / Terminal shutdown protections for the camera runtime."""

import asyncio
import importlib
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import numpy as np
import pytest
import pytest_asyncio

from ogscope.application import camera as composition
from ogscope.application.camera_control import CameraControlService
from ogscope.application.camera_manager import CameraManager
from ogscope.domain.camera.runtime import CameraRuntime, SharedFrame


class Camera:
    """记录原生操作顺序的设备替身 / Device double that records native operation order."""

    is_initialized = True

    def __init__(self):
        self.is_capturing = True
        self.events = []

    def start_capture(self):
        self.events.append("start")
        self.is_capturing = True
        return True

    def stop_capture(self):
        self.events.append("stop")
        self.is_capturing = False
        return True

    def close(self):
        self.events.append("close")
        return True

    def get_camera_info(self):
        return {"sensor": "test", "width": 4, "height": 4, "fps": 8}

    def get_video_frame(self):
        return np.zeros((4, 4, 3), dtype=np.uint8)


@pytest_asyncio.fixture
async def runtime_manager():
    manager = CameraManager()
    camera = Camera()
    manager.attach_camera_instance(camera)
    manager._frames.health.last_success_mono = time.monotonic()
    manager._idle_shutdown_sec = 120
    try:
        yield manager, camera
    finally:
        if not manager._resources.executors_closed:
            await manager.shutdown()
        manager._resources.capture_executor.shutdown(wait=True)
        manager._resources.jpeg_executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_stop_remains_reusable_but_terminal_close_is_idempotent(
    runtime_manager, monkeypatch
):
    manager, first = runtime_manager
    second = Camera()
    monkeypatch.setattr(manager, "_create_camera_sync", lambda: second)
    await manager.stop()
    assert first.events == ["stop", "close"]
    await manager.ensure_started()
    assert manager.get_camera_instance() is second
    lease = manager.update_operation_lease(ttl_seconds=60)
    assert lease
    await manager.shutdown()
    await manager.shutdown()
    await manager.release_preview_consumer()
    await manager.release_analysis_consumer()
    assert second.events == ["stop", "close"]
    assert manager.get_camera_instance() is None
    assert manager.lifecycle_status()["operation_consumers"] == 0
    assert not manager._resources.background_tasks
    assert not manager._resources.worker_futures
    for operation in (
        manager.ensure_started,
        manager.acquire_preview_consumer,
        manager.acquire_analysis_consumer,
        manager.acquire_recording_consumer,
        lambda: manager.encode_image(None),
        lambda: manager.reset_temporal_history(second),
    ):
        with pytest.raises(RuntimeError, match="shutting down"):
            await operation()
    with pytest.raises(RuntimeError, match="shutting down"):
        manager.update_operation_lease()
    with pytest.raises(RuntimeError, match="shutting down"):
        manager.attach_camera_instance(Camera())
    assert all(
        manager.lifecycle_status()[name] == 0
        for name in ("preview_consumers", "analysis_consumers", "recording_consumers")
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("work", ["raw", "variant", "image"])
async def test_cancelled_request_keeps_native_work_until_shutdown_drains(
    runtime_manager, monkeypatch, work
):
    manager, camera = runtime_manager
    entered, release = threading.Event(), threading.Event()

    def blocked(*args):
        entered.set()
        assert release.wait(3)
        camera.events.append("worker-done")
        return np.zeros((4, 4, 3), dtype=np.uint8) if work == "raw" else b"jpeg"

    if work == "raw":
        monkeypatch.setattr(camera, "get_video_frame", blocked)
        request = asyncio.create_task(manager.get_raw_frame())
    elif work == "variant":
        monkeypatch.setattr(manager._frames, "_encode_stream_jpeg_sync", blocked)
        snap = SharedFrame(1, 0, None, b"jpeg", 4, 4)
        request = asyncio.create_task(manager.get_stream_jpeg(snap, 42))
    else:
        monkeypatch.setattr(manager._frames, "encode_frame", blocked)
        request = asyncio.create_task(manager.encode_image(None, "png"))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request
        closing = asyncio.create_task(manager.shutdown())
        await asyncio.sleep(0.02)
        assert not closing.done()
        assert "close" not in camera.events
        assert any(not future.done() for future in manager._resources.worker_futures)
        release.set()
        await closing
        assert camera.events == ["worker-done", "stop", "close"]
        assert not manager._resources.worker_futures
        assert not manager._resources.background_tasks
    finally:
        release.set()


@pytest.mark.asyncio
async def test_cancelling_shutdown_waiter_does_not_interrupt_native_close(
    runtime_manager, monkeypatch
):
    manager, camera = runtime_manager
    entered, release = threading.Event(), threading.Event()

    def blocked_close():
        entered.set()
        assert release.wait(3)
        camera.events.append("close")
        return True

    monkeypatch.setattr(camera, "close", blocked_close)
    try:
        closing = asyncio.create_task(manager.shutdown())
        assert await asyncio.to_thread(entered.wait, 1)
        closing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await closing
        assert manager.get_camera_instance() is camera
        release.set()
        await manager.shutdown()
        assert camera.events == ["stop", "close"]
        assert manager.get_camera_instance() is None
    finally:
        release.set()


@pytest.mark.asyncio
async def test_terminal_timeout_retains_handle_and_never_claims_release(
    runtime_manager, monkeypatch
):
    manager, camera = runtime_manager
    from ogscope.application import camera_manager as implementation

    receipt = Mock()
    monkeypatch.setattr(implementation, "event_logger", SimpleNamespace(info=receipt))
    entered, release = threading.Event(), threading.Event()

    def blocked_read():
        entered.set()
        assert release.wait(3)
        return np.zeros((4, 4, 3), dtype=np.uint8)

    monkeypatch.setattr(camera, "get_video_frame", blocked_read)
    request = asyncio.create_task(manager.get_raw_frame())
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request
        started = time.monotonic()
        with pytest.raises(RuntimeError, match="incomplete"):
            await manager.shutdown(timeout_sec=0.05)
        assert time.monotonic() - started < 0.5
        assert receipt.call_args.args[1] is False
        assert receipt.call_args.args[2] == 1
        assert manager.get_camera_instance() is camera
        assert manager._restart_required
        assert camera.events == []
        release.set()
        await asyncio.gather(*manager._resources.worker_futures)
        with pytest.raises(RuntimeError, match="incomplete"):
            await manager.shutdown()
        assert camera.events == []
        with pytest.raises(RuntimeError, match="shutting down"):
            await manager.ensure_started()
    finally:
        release.set()


@pytest.mark.asyncio
async def test_failed_close_is_not_retried_by_duplicate_terminal_shutdown(
    runtime_manager, monkeypatch
):
    manager, camera = runtime_manager
    close = Mock(return_value=False)
    monkeypatch.setattr(camera, "close", close)
    for _ in range(2):
        with pytest.raises(RuntimeError, match="incomplete"):
            await manager.shutdown()
    assert close.call_count == 1
    assert manager.get_camera_instance() is camera
    assert manager._restart_required


@pytest.mark.asyncio
async def test_shutdown_joins_late_warmup_handle_without_starting_capture(
    runtime_manager, monkeypatch
):
    manager, camera = runtime_manager
    manager._camera = None
    camera.is_capturing = False
    entered, release = threading.Event(), threading.Event()

    def create():
        entered.set()
        assert release.wait(3)
        return camera

    monkeypatch.setattr(manager, "_create_camera_sync", create)
    try:
        manager.start_warmup()
        assert await asyncio.to_thread(entered.wait, 1)
        closing = asyncio.create_task(manager.shutdown())
        await asyncio.sleep(0.02)
        assert not closing.done()
        release.set()
        await closing
        assert "start" not in camera.events
        assert camera.events[-1] == "close"
        assert manager.get_camera_instance() is None
        assert not manager._resources.background_tasks
    finally:
        release.set()


@pytest.mark.asyncio
async def test_terminal_close_joins_idle_close_already_in_native_stop(
    runtime_manager, monkeypatch
):
    manager, camera = runtime_manager
    entered, release = threading.Event(), threading.Event()

    def stop():
        entered.set()
        assert release.wait(3)
        camera.events.append("stop")
        camera.is_capturing = False
        return True

    monkeypatch.setattr(camera, "stop_capture", stop)
    try:
        manager._idle_shutdown_sec = 0.01
        await manager.ensure_started()
        assert await asyncio.to_thread(entered.wait, 1)
        closing = asyncio.create_task(manager.shutdown())
        await asyncio.sleep(0.02)
        release.set()
        await closing
        assert camera.events == ["stop", "close"]
        assert not manager._restart_required
    finally:
        release.set()


@pytest.mark.asyncio
async def test_recording_task_and_ownership_are_released_on_terminal_close(
    runtime_manager,
):
    manager, _ = runtime_manager
    control = CameraControlService(manager, analysis_running=lambda: False)
    released = asyncio.Event()
    await manager.acquire_recording_consumer()
    control.recording = True

    async def record():
        try:
            while control.recording:
                await asyncio.sleep(0)
        finally:
            released.set()

    control.recording_task = asyncio.create_task(record())
    await asyncio.sleep(0)
    await control.shutdown()
    await control.shutdown()
    assert released.is_set()
    assert control.recording_task is None
    assert manager.lifecycle_status()["recording_consumers"] == 0


@pytest.mark.asyncio
async def test_runtime_shutdown_attempts_every_stage_once_after_consumer_error(
    monkeypatch,
):
    from ogscope.core.realtime import realtime_solve_service

    events = []

    async def solve_stop(**kwargs):
        events.append("analysis")
        raise RuntimeError("consumer failure")

    async def recording_stop():
        events.append("recording")

    async def capture_stop():
        events.append("capture")

    capture = SimpleNamespace(
        begin_shutdown=lambda: events.append("fence"), shutdown=capture_stop
    )
    control = SimpleNamespace(shutdown=recording_stop)
    monkeypatch.setattr(composition, "_runtime", CameraRuntime(capture, control))
    monkeypatch.setattr(composition, "_shutdown_task", None)
    monkeypatch.setattr(realtime_solve_service, "stop", solve_stop)
    for _ in range(2):
        with pytest.raises(RuntimeError, match="consumer failure"):
            await composition.shutdown_camera_runtime()
    assert events == ["fence", "analysis", "recording", "capture"]
    assert not composition._shutdown_children


@pytest.mark.asyncio
async def test_unused_runtime_is_not_constructed_for_shutdown(monkeypatch):
    monkeypatch.setattr(composition, "_runtime", None)
    factory = Mock(side_effect=AssertionError("must not create hardware"))
    monkeypatch.setattr(composition, "get_camera_runtime", factory)
    await composition.shutdown_camera_runtime()
    factory.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("startup_failure", [False, True])
async def test_application_lifespan_closes_camera_and_hardware_on_startup_failure(
    monkeypatch, startup_failure
):
    web = importlib.import_module("ogscope.web.app")
    from ogscope.algorithms.plate_solve import solver
    from ogscope.utils import environment

    events = []
    daemon = SimpleNamespace(begin_phase=Mock())
    if startup_failure:
        daemon.begin_phase.side_effect = RuntimeError("startup failure")
    monkeypatch.setattr(web, "start_hardware_plane", AsyncMock())
    monkeypatch.setattr(web, "get_hardware_plane_daemon", lambda: daemon)
    monkeypatch.setattr(
        web,
        "stop_hardware_plane",
        AsyncMock(side_effect=lambda: events.append("hardware")),
    )
    monkeypatch.setattr(
        web, "migrate_legacy_dev_captures", lambda: {"migrated": [], "errors": []}
    )
    monkeypatch.setattr(solver, "warmup_tetra3", lambda: None)
    monkeypatch.setattr(environment, "should_use_simulation_mode", lambda: True)
    monkeypatch.setattr(web.get_settings(), "hardware_plane_camera_autostart", False)
    monkeypatch.setattr(
        composition,
        "shutdown_camera_runtime",
        AsyncMock(side_effect=lambda: events.append("camera")),
    )
    if startup_failure:
        with pytest.raises(RuntimeError, match="startup failure"):
            async with web.lifespan(web.app):
                pytest.fail("startup must fail")
    else:
        async with web.lifespan(web.app):
            assert events == []
    assert events == ["camera", "hardware"]


@pytest.mark.asyncio
async def test_terminal_shutdown_drains_active_preview_and_lease_timer(runtime_manager):
    manager, camera = runtime_manager
    await manager.acquire_preview_consumer()
    manager.update_operation_lease(ttl_seconds=60)
    code, frame = await manager.get_preview_frame(wait_timeout_sec=1)
    assert code == 200 and frame.jpeg_frame
    await manager.shutdown()
    assert camera.events == ["stop", "close"]
    assert manager.lifecycle_status()["preview_consumers"] == 0
    assert not manager._resources.background_tasks
    assert not manager._resources.worker_futures


@pytest.mark.asyncio
async def test_warmup_timeout_quarantines_handle_arriving_after_shutdown(
    runtime_manager, monkeypatch
):
    manager, camera = runtime_manager
    manager._camera = None
    entered, release = threading.Event(), threading.Event()

    def create():
        entered.set()
        assert release.wait(3)
        return camera

    monkeypatch.setattr(manager, "_create_camera_sync", create)
    try:
        manager.start_warmup()
        assert await asyncio.to_thread(entered.wait, 1)
        with pytest.raises(RuntimeError, match="incomplete"):
            await manager.shutdown(timeout_sec=0.05)
        release.set()
        await asyncio.gather(*manager._resources.worker_futures)
        assert manager.get_camera_instance() is camera
        assert manager._restart_required
        assert camera.events == []
        with pytest.raises(RuntimeError, match="shutting down"):
            await manager.ensure_started()
    finally:
        release.set()


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", [False, True])
async def test_dev_recording_writer_cleanup_and_normal_sidecar_are_preserved(
    runtime_manager, monkeypatch, tmp_path, terminal
):
    import cv2

    from ogscope.web.api.debug import services

    manager, _ = runtime_manager
    control = CameraControlService(manager, analysis_running=lambda: False)
    monkeypatch.setattr(composition, "_runtime", CameraRuntime(manager, control))
    monkeypatch.setattr(services, "DEBUG_CAPTURES_DIR", tmp_path)
    writer = SimpleNamespace(isOpened=lambda: True, write=Mock(), release=Mock())
    monkeypatch.setattr(cv2, "VideoWriter", lambda *args: writer)
    sidecar = Mock()
    monkeypatch.setattr(services, "save_capture_sidecar", sidecar)
    result = await services.DebugCameraService.start_recording()
    assert result["success"]
    await asyncio.sleep(0)
    if terminal:
        manager.begin_shutdown()
        await control.shutdown()
    else:
        assert (await services.DebugCameraService.stop_recording())["success"]
    writer.release.assert_called_once()
    assert sidecar.call_count == (0 if terminal else 1)
    assert control.recording_task is None
    assert manager.lifecycle_status()["recording_consumers"] == 0


@pytest.mark.asyncio
async def test_cancelled_recording_stop_still_releases_writer_and_ownership(
    runtime_manager, monkeypatch, tmp_path
):
    from ogscope.web.api.debug import services

    manager, _ = runtime_manager
    control = CameraControlService(manager, analysis_running=lambda: False)
    monkeypatch.setattr(composition, "_runtime", CameraRuntime(manager, control))
    monkeypatch.setattr(services, "DEBUG_CAPTURES_DIR", tmp_path)
    monkeypatch.setattr(services, "recording_stem", None)
    released = asyncio.Event()
    await manager.acquire_recording_consumer()
    control.recording = True

    async def record():
        try:
            await asyncio.Event().wait()
        finally:
            released.set()

    control.recording_task = asyncio.create_task(record())
    stopping = asyncio.create_task(services.DebugCameraService.stop_recording())
    await asyncio.sleep(0)
    stopping.cancel()
    assert (await stopping)["success"]
    assert released.is_set()
    assert control.recording_task is None
    assert manager.lifecycle_status()["recording_consumers"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["start", "probe"])
async def test_cancelled_startup_quarantines_pending_native_work(
    runtime_manager, monkeypatch, phase
):
    """启动或探测取消时禁止重复获取原生设备 / Fence reacquisition after cancelled native start or probe."""
    manager, camera = runtime_manager
    entered, release = threading.Event(), threading.Event()
    camera.is_capturing = phase == "probe"
    manager._frames.health.last_success_mono = 0

    def blocked(*args):
        entered.set()
        release.wait(timeout=3)
        camera.is_capturing = True
        return True

    monkeypatch.setattr(
        camera if phase == "start" else manager,
        "start_capture" if phase == "start" else "_probe_stream_health_sync",
        blocked,
    )
    starting = asyncio.create_task(manager.ensure_started())
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        starting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await starting
        assert manager.get_camera_instance() is camera
        assert (await manager.status())["restart_required"] is True
        with pytest.raises(RuntimeError, match="cancelled"):
            await manager.ensure_started()
    finally:
        release.set()
        await asyncio.gather(starting, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["start", "probe"])
async def test_ordinary_stop_waits_for_cancelled_startup_worker(
    runtime_manager, monkeypatch, phase
):
    """普通停止也须等待取消后的原生启动/探测 / Reusable stop must drain cancelled native start/probe work too."""
    manager, camera = runtime_manager
    entered, release = threading.Event(), threading.Event()
    camera.is_capturing = phase == "probe"
    manager._frames.health.last_success_mono = 0

    def blocked(*args):
        entered.set()
        release.wait(timeout=3)
        camera.events.append("native_finished")
        camera.is_capturing = True
        return True

    monkeypatch.setattr(
        camera if phase == "start" else manager,
        "start_capture" if phase == "start" else "_probe_stream_health_sync",
        blocked,
    )
    starting = asyncio.create_task(manager.ensure_started())
    stopping = None
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        starting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await starting
        stopping = asyncio.create_task(manager.stop())
        await asyncio.sleep(0.05)
        assert "close" not in camera.events
        assert not stopping.done()
        release.set()
        await asyncio.wait_for(stopping, 1)
        assert camera.events == ["native_finished", "stop", "close"]
        assert manager.get_camera_instance() is None
    finally:
        release.set()
        await asyncio.gather(
            *(task for task in (starting, stopping) if task is not None),
            return_exceptions=True,
        )


@pytest.mark.asyncio
async def test_cancelled_reconfiguration_does_not_resume_capture(
    runtime_manager, monkeypatch
):
    """改参等待取消后不能恢复抓帧或重复获取 / Cancelled reconfiguration must not resume capture or allow reacquisition."""
    manager, camera = runtime_manager
    entered, release = threading.Event(), threading.Event()
    resume = AsyncMock()
    monkeypatch.setattr(manager._frames, "start", resume)

    def blocked():
        entered.set()
        release.wait(timeout=3)
        camera.events.append("reconfigured")

    changing = asyncio.create_task(manager.reconfigure_camera("test", blocked))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        changing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await changing
        resume.assert_not_awaited()
        assert (await manager.status())["restart_required"] is True
        with pytest.raises(RuntimeError, match="cancelled"):
            await manager.ensure_started()
        release.set()
        await manager.stop()
        assert camera.events == ["reconfigured", "stop", "close"]
    finally:
        release.set()
        await asyncio.gather(changing, return_exceptions=True)
