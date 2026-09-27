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
def test_start_seeds_loop_baseline_from_currently_cached_frame(monkeypatch) -> None:
    """启动必须跳过启动前缓存里的旧帧 / Starting a session must skip the frame already cached from before it.

    The camera keeps capturing between sessions (for the live preview), so
    whatever frame is cached when start() is called may have been taken
    during/before mount settling. The loop must not treat that already-
    cached frame as this session's fresh first frame - it needs to wait for
    a strictly newer frame_id.
    """
    from ogscope.core.realtime import service as realtime_service_module
    from ogscope.core.realtime.service import RealtimeSolveService

    service = RealtimeSolveService()

    class _FakeManager:
        async def get_raw_frame(self):
            return np.zeros((4, 4, 3), dtype=np.uint8), 7, 0.0

        def get_camera_instance(self):
            return None

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
def test_start_resets_camera_temporal_history_for_the_new_epoch(
    monkeypatch,
) -> None:
    """启动必须让驱动清除跨帧历史 / Starting a session must tell the driver to
    discard cross-frame history (e.g. temporal-NR EMA), not just wait for a
    newer frame_id.

    A newer frame_id alone doesn't guarantee the frame's content carries no
    old history: the camera keeps capturing through a mount move, and the
    V4L2 backend's EMA accumulator used to reset only on an exposure/gain
    change or a physical camera (re)start. start() must call the driver's
    begin_fresh_capture_epoch hook so the first frame of a new session is
    never blended with frames from before the mount settled.
    """
    from ogscope.core.realtime import service as realtime_service_module
    from ogscope.core.realtime.service import RealtimeSolveService

    service = RealtimeSolveService()
    epoch_calls = 0

    class _FakeCameraWithEpochHook:
        def begin_fresh_capture_epoch(self) -> None:
            nonlocal epoch_calls
            epoch_calls += 1

    camera = _FakeCameraWithEpochHook()

    class _FakeManager:
        async def get_raw_frame(self):
            return np.zeros((4, 4, 3), dtype=np.uint8), 7, 0.0

        def get_camera_instance(self):
            return camera

    monkeypatch.setattr(
        realtime_service_module, "get_camera_manager", lambda: _FakeManager()
    )

    async def _fake_loop(self, initial_frame_id: int = -1) -> None:
        return None

    monkeypatch.setattr(RealtimeSolveService, "_loop", _fake_loop)

    async def _run() -> None:
        await service.start()
        await asyncio.sleep(0)

    asyncio.run(_run())

    assert epoch_calls == 1


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
