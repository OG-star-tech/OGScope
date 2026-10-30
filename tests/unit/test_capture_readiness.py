"""Wake, exposure and ownership regressions / 唤醒、曝光与任务占用回归测试。"""

import asyncio
import time
from types import SimpleNamespace

import numpy as np
import pytest

from ogscope.core.realtime import service as realtime
from ogscope.core.realtime.service import RealtimeSolveService
from ogscope.domain.camera.readiness import CaptureReadiness
from ogscope.web.camera_shared import CameraManager


def test_ae_search_and_queued_frames_never_count_as_ready():
    tracker = CaptureReadiness()
    for index in range(1, 7):
        tracker.observe(
            index,
            {
                "auto_exposure": True,
                "ae_state": "adjusting",
                "ae_phase": "searching_dark",
                "actual_exposure_us": 100_000,
            },
        )
        assert not tracker.snapshot()["ready"]
    tracker.observe(7, {"ae_state": "settling", "actual_exposure_us": 3_000_000})
    assert not tracker.snapshot()["ready"]
    tracker.observe(8, {"ae_state": "converged", "actual_exposure_us": 3_000_000})
    assert tracker.snapshot()["ready"]


def test_metadata_stability_uses_distinct_frames_and_resets_after_sleep():
    tracker = CaptureReadiness()
    info = {
        "auto_exposure": True,
        "actual_exposure_us": 1000,
        "actual_analogue_gain": 2,
    }
    for _ in range(10):
        tracker.observe(1, info)
    assert not tracker.snapshot()["ready"]
    tracker.observe(2, info)
    assert not tracker.snapshot()["ready"]
    tracker.observe(3, info)
    assert tracker.snapshot()["ready"]
    tracker.observe(4, {**info, "actual_exposure_us": 10_000})
    assert not tracker.snapshot()["ready"]
    tracker.reset()
    assert tracker.snapshot()["frame_sequence"] == -1
    assert not tracker.snapshot()["ready"]


@pytest.mark.parametrize(
    "info,reason",
    [
        ({"auto_exposure": False}, "manual"),
        ({"ae_state": "limited_dark", "actual_exposure_us": 3_000_000}, "limited_dark"),
    ],
)
def test_manual_and_dark_limit_do_not_wait_for_stars(info, reason):
    tracker = CaptureReadiness()
    tracker.observe(1, info)
    assert tracker.snapshot()["ready"]
    assert tracker.snapshot()["reason"] == reason


def test_unknown_metadata_is_explicit_and_pending_mode_is_not_ready():
    tracker = CaptureReadiness()
    for sequence in range(3):
        tracker.observe(sequence, {})
    assert tracker.snapshot()["reason"] == "metadata_unavailable"
    tracker.observe(4, {"ae_exposure_mode_status": "awaiting_metadata"})
    assert not tracker.snapshot()["ready"]


@pytest.mark.asyncio
async def test_task_lease_prevents_idle_sleep_and_release_does_not_stop_preview(
    monkeypatch,
):
    manager = CameraManager()
    manager._idle_shutdown_sec = 0.01
    stopped = []

    async def stop():
        stopped.append(True)

    monkeypatch.setattr(manager, "stop", stop)
    lease = manager.update_operation_lease(ttl_seconds=10)
    manager._schedule_idle_shutdown()
    await asyncio.sleep(0.02)
    assert not stopped
    manager._preview_consumers = 1
    manager.update_operation_lease(lease_id=lease["lease_id"], release=True)
    await asyncio.sleep(0.02)
    assert not stopped
    manager._preview_consumers = 0
    manager._schedule_idle_shutdown()
    await asyncio.sleep(0.02)
    assert stopped == [True]


@pytest.mark.asyncio
async def test_lost_owner_expires_and_cannot_be_silently_renewed():
    manager = CameraManager()
    manager._idle_shutdown_sec = 0
    acquired = manager.update_operation_lease(ttl_seconds=10)
    token = acquired["lease_id"]
    manager._operation_leases[token] = time.monotonic() - 1
    assert manager.update_operation_lease(lease_id=token)["success"] is False
    await asyncio.sleep(0.02)
    assert manager.lifecycle_status()["operation_consumers"] == 0
    manager.update_operation_lease(lease_id=token, release=True)
    await asyncio.sleep(0)


class ExposureCamera:
    """Completed-frame metadata changes from search to stable / 完成帧元数据从搜索变为稳定。"""

    is_initialized = True
    is_capturing = False

    def __init__(self):
        self.frames = 0

    def start_capture(self):
        self.is_capturing = True
        return True

    def stop_capture(self):
        self.is_capturing = False
        return True

    def get_video_frame(self):
        self.frames += 1
        return np.zeros((16, 16, 3), dtype=np.uint8)

    def get_camera_info(self):
        return {
            "actual_exposure_us": 3_000_000,
            "ae_state": "converged" if self.frames >= 4 else "settling",
        }


@pytest.mark.asyncio
async def test_cold_analysis_waits_without_spending_solve_attempts(monkeypatch):
    manager = CameraManager()
    manager._idle_shutdown_sec = 0
    camera = ExposureCamera()
    manager.attach_camera_instance(camera)
    monkeypatch.setattr(realtime, "get_camera_manager", lambda: manager)
    solver = RealtimeSolveService()
    entered = asyncio.Event()

    async def solve(*_):
        assert camera.frames >= 4
        assert solver.state.fullsolve_count == 0
        assert solver.state.phase == "analyzing"
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(solver, "_run_loop", solve)
    await solver.start()
    await asyncio.wait_for(entered.wait(), 1)
    await solver.stop()
    await asyncio.sleep(0.02)
    assert manager._analysis_consumers == 0


@pytest.mark.asyncio
async def test_exposure_preparation_has_a_deadline_and_no_solver_calls(monkeypatch):
    now = [0.0]

    def tick():
        now[0] += 5
        return now[0]

    monkeypatch.setattr(realtime, "time", SimpleNamespace(monotonic=tick))
    tracker = CaptureReadiness()

    async def frame():
        return object(), now[0], 0

    solver = RealtimeSolveService()
    solver.state.running = True
    with pytest.raises(RuntimeError, match="CAMERA_NOT_READY"):
        await solver._prepare_camera(
            SimpleNamespace(analysis_readiness=tracker, get_raw_frame=frame)
        )
    assert solver.state.fullsolve_count == 0


@pytest.mark.asyncio
async def test_cancelling_during_exposure_preparation_releases_owner(monkeypatch):
    from unittest.mock import AsyncMock

    manager = CameraManager()
    manager._idle_shutdown_sec = 0
    entered = asyncio.Event()

    async def waiting():
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(manager, "ensure_started", AsyncMock())
    monkeypatch.setattr(manager, "get_raw_frame", waiting)
    monkeypatch.setattr(realtime, "get_camera_manager", lambda: manager)
    service = RealtimeSolveService()
    await service.start()
    await asyncio.wait_for(entered.wait(), 1)
    await service.stop()
    await asyncio.sleep(0.01)
    assert manager._analysis_consumers == 0
    assert service.state.fullsolve_count == 0
    assert service.state.phase == "stopped"


@pytest.mark.asyncio
async def test_busy_core_stop_never_bypasses_domain_guard(monkeypatch):
    from unittest.mock import AsyncMock

    from ogscope.core.application import core_service

    monkeypatch.setattr(
        core_service.camera_domain_service,
        "stop",
        AsyncMock(return_value={"success": False, "message": "Camera is in use"}),
    )
    command = AsyncMock()
    monkeypatch.setattr(
        core_service,
        "get_hardware_plane_client",
        lambda: SimpleNamespace(device_command=command),
    )
    result = await core_service.CoreContractService().stop_camera()
    assert result["success"] is False
    command.assert_not_awaited()


def test_camera_lease_request_rejects_unbounded_input():
    from pydantic import ValidationError

    from ogscope.web.api.models.schemas import CoreCameraLeaseRequest

    for invalid in ({"ttl_seconds": 121}, {"ttl_seconds": 0}, {"unknown": True}):
        with pytest.raises(ValidationError):
            CoreCameraLeaseRequest(**invalid)


@pytest.mark.asyncio
async def test_exposure_control_failure_is_not_treated_as_stability():
    from ogscope.domain.camera.readiness import wait_capture_ready

    tracker = CaptureReadiness()
    for number in range(5):
        tracker.observe(
            number, {"ae_state": "control_error", "actual_exposure_us": 1000}
        )
    assert not tracker.snapshot()["ready"]
    with pytest.raises(RuntimeError, match="exposure control failed"):
        await wait_capture_ready(SimpleNamespace(analysis_readiness=tracker))


@pytest.mark.asyncio
async def test_missing_camera_frames_end_session_without_retaining_result(monkeypatch):
    now = [0.0]

    def tick():
        now[0] += 10
        return now[0]

    monkeypatch.setattr(realtime, "time", SimpleNamespace(monotonic=tick))
    service = RealtimeSolveService()
    service.state.running = True
    service.state.last_result = {"status": "MATCH_FOUND"}
    service._snapshot = object()
    await service._run_loop(SimpleNamespace(get_camera_instance=lambda: None))
    assert not service.state.running
    assert service.state.phase == "failed"
    assert service.state.last_result is None
    assert service.get_solve_frame_snapshot() is None
    assert service.state.fullsolve_count == 0


@pytest.mark.asyncio
async def test_hardware_plane_cannot_close_capture_owned_by_a_task(monkeypatch):
    from ogscope.platform.hardware_plane.services.camera_service import (
        CameraPlaneService,
    )

    manager = CameraManager()
    manager._idle_shutdown_sec = 0
    lease = manager.update_operation_lease()
    monkeypatch.setattr(
        "ogscope.application.camera.get_camera_capture", lambda: manager
    )
    result = await CameraPlaneService().command("stop")
    assert result["accepted"] is False
    manager.update_operation_lease(lease_id=lease["lease_id"], release=True)
    await asyncio.sleep(0.01)
