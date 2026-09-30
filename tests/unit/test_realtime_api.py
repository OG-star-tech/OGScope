"""
实时解算 API 测试 / Realtime solving API tests
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pytest


@dataclass
class _FakeCamera:
    """测试相机 / Test camera"""

    is_capturing: bool = True

    def get_video_frame(self):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        frame[120, 160] = (255, 255, 255)
        frame[60, 100] = (255, 255, 255)
        return frame

    def get_camera_info(self):
        return {"actual_exposure_us": 1_000_000}


@pytest.mark.unit
def test_capture_time_payload_uses_exposure_midpoint() -> None:
    """解算时刻取曝光中点而非解算完成时刻 / Use exposure midpoint, not solve completion."""
    from ogscope.core.realtime.service import RealtimeSolveService

    completed = datetime(2026, 9, 1, 15, 0, 1, tzinfo=timezone.utc).timestamp()
    payload = RealtimeSolveService._capture_time_payload(
        completed,
        {"actual_exposure_us": 1_000_000},
    )

    assert payload["observation_time_utc"] == "2026-09-01T15:00:00.500000Z"
    assert payload["capture_completed_at_utc"] == "2026-09-01T15:00:01Z"
    assert payload["capture_exposure_us"] == 1_000_000


@pytest.mark.unit
def test_start_seeds_loop_baseline_when_still_within_a_fresh_epoch(
    monkeypatch,
) -> None:
    """刚结算过移动时必须跳过缓存里的旧帧 / Right after a real settle, starting
    a session must skip the frame already cached from before it.

    The camera keeps capturing between sessions (for the live preview), so
    whatever frame is cached when start() is called may have been taken
    during/before mount settling. While the driver reports we're still
    inside that risk window (a real settle happened recently), the loop
    must not treat the already-cached frame as this session's fresh first
    frame - it needs to wait for a strictly newer frame_id.
    """
    from ogscope.core.realtime import service as realtime_service_module
    from ogscope.core.realtime.service import RealtimeSolveService

    service = RealtimeSolveService()

    class _FakeCameraStillFresh:
        def is_within_fresh_capture_epoch(self) -> bool:
            return True

    camera = _FakeCameraStillFresh()

    class _FakeManager:
        def get_current_capture_sequence(self) -> int:
            return 7

        def get_camera_instance(self):
            return camera

    monkeypatch.setattr(
        realtime_service_module, "get_camera_manager", lambda: _FakeManager()
    )

    captured: dict[str, int] = {}

    async def _fake_loop(self, initial_frame_id: int = -1) -> None:
        captured["initial_frame_id"] = initial_frame_id

    monkeypatch.setattr(RealtimeSolveService, "_loop", _fake_loop)

    async def _run() -> None:
        await service.start()
        # start() only schedules _loop as a task; yield once so it runs.
        await asyncio.sleep(0)

    asyncio.run(_run())

    assert captured["initial_frame_id"] == 7


@pytest.mark.unit
def test_start_skips_the_fresh_frame_wait_for_a_retry_at_an_unchanged_pose(
    monkeypatch,
) -> None:
    """同姿态重试不应该再等一帧全新的 / A retry at an unchanged pose must not
    wait for another brand-new frame.

    Regression for "repeated retries at the same pose were barely
    capturing a frame at all": every _single_solve() attempt restarts the
    OGScope analysis session, and previously start() always demanded a
    frame newer than whatever was already cached - even when no real
    settle had happened since the last attempt, forcing every retry to pay
    a full exposure's wait. Once the driver reports we're past its fresh
    window (no real settle recently), start() must accept the current
    session id and start_gate immediately (baseline -1), never touching
    get_current_capture_sequence() at all.
    """
    from ogscope.core.realtime import service as realtime_service_module
    from ogscope.core.realtime.service import RealtimeSolveService

    service = RealtimeSolveService()

    class _FakeCameraNotFresh:
        def is_within_fresh_capture_epoch(self) -> bool:
            return False

    camera = _FakeCameraNotFresh()

    class _FakeManager:
        def get_current_capture_sequence(self) -> int:
            raise AssertionError(
                "start() must not need the capture sequence when the "
                "driver reports the cached frame is already safe"
            )

        def get_camera_instance(self):
            return camera

    monkeypatch.setattr(
        realtime_service_module, "get_camera_manager", lambda: _FakeManager()
    )

    captured: dict[str, int] = {}

    async def _fake_loop(self, initial_frame_id: int = -1) -> None:
        captured["initial_frame_id"] = initial_frame_id

    monkeypatch.setattr(RealtimeSolveService, "_loop", _fake_loop)

    async def _run() -> None:
        await service.start()
        await asyncio.sleep(0)

    asyncio.run(_run())

    assert captured["initial_frame_id"] == -1


@pytest.mark.unit
def test_start_never_calls_the_slow_synchronous_frame_grab(monkeypatch) -> None:
    """回归：start() 建立基线绝不能触发同步抓帧 / Regression: establishing
    the baseline in start() must never fall through to a synchronous
    camera capture.

    Without a resident raw cache (the default), get_raw_frame() blocks on a
    real capture - which can mean waiting out whatever exposure the
    background grabber is currently holding and then grabbing another.
    Measured on real hardware, that stretched a single analysis/start call
    past 8-10 seconds, well past the caller's own HTTP read timeout, so
    every attempt timed out and was retried before any session ever lived
    long enough to solve a single frame. start() must get its baseline
    without going anywhere near get_raw_frame().
    """
    from ogscope.core.realtime import service as realtime_service_module
    from ogscope.core.realtime.service import RealtimeSolveService

    service = RealtimeSolveService()

    class _FakeCameraStillFresh:
        def is_within_fresh_capture_epoch(self) -> bool:
            return True

    camera = _FakeCameraStillFresh()

    class _FakeManager:
        def get_current_capture_sequence(self) -> int:
            return 3

        def get_camera_instance(self):
            return camera

        async def get_raw_frame(self):
            raise AssertionError(
                "start() must not call get_raw_frame() - it can block on a "
                "real capture for as long as the current exposure"
            )

    monkeypatch.setattr(
        realtime_service_module, "get_camera_manager", lambda: _FakeManager()
    )

    captured: dict[str, int] = {}

    async def _fake_loop(self, initial_frame_id: int = -1) -> None:
        captured["initial_frame_id"] = initial_frame_id

    monkeypatch.setattr(RealtimeSolveService, "_loop", _fake_loop)

    async def _run() -> None:
        await service.start()
        await asyncio.sleep(0)

    asyncio.run(_run())

    assert captured["initial_frame_id"] == 3


@pytest.mark.unit
def test_realtime_solver_status_endpoints(client, monkeypatch, mock_plate_solve):
    """测试实时解算启停接口 / Test realtime solver start and stop endpoints."""
    from ogscope.web.api.debug import routes as debug_routes
    from ogscope.web.camera_shared import CameraManager, get_camera_manager

    fake_camera = _FakeCamera()
    get_camera_manager().attach_camera_instance(fake_camera)
    monkeypatch.setattr(
        debug_routes.DebugCameraService,
        "get_camera_instance",
        staticmethod(lambda: fake_camera),
    )

    async def _fake_get_raw_frame(_self):
        frame = fake_camera.get_video_frame()
        return frame, 1, 0.0

    monkeypatch.setattr(CameraManager, "get_raw_frame", _fake_get_raw_frame)

    start_resp = client.post(
        "/api/dev/debug/analysis/realtime/start",
        params={"hint_ra_deg": 15.0, "hint_dec_deg": 85.0},
    )
    assert start_resp.status_code == 200
    assert start_resp.json()["success"] is True

    asyncio.run(asyncio.sleep(0.05))

    status_resp = client.get("/api/dev/debug/analysis/realtime/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert "running" in status_data
    assert "frame_count" in status_data

    stop_resp = client.post("/api/dev/debug/analysis/realtime/stop")
    assert stop_resp.status_code == 200
    assert stop_resp.json()["success"] is True
