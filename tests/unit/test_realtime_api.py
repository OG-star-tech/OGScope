"""
实时解算 API 测试 / Realtime solving API tests
"""

import asyncio
from dataclasses import dataclass

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
        "/api/debug/analysis/realtime/start",
        params={"hint_ra_deg": 15.0, "hint_dec_deg": 85.0},
    )
    assert start_resp.status_code == 200
    assert start_resp.json()["success"] is True

    asyncio.run(asyncio.sleep(0.05))

    status_resp = client.get("/api/debug/analysis/realtime/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert "running" in status_data
    assert "frame_count" in status_data

    stop_resp = client.post("/api/debug/analysis/realtime/stop")
    assert stop_resp.status_code == 200
    assert stop_resp.json()["success"] is True
