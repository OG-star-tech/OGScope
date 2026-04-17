"""
Core 标准契约 API 测试 / Core standard contract API tests.
"""

from __future__ import annotations

import pytest
from fastapi.responses import Response


@pytest.mark.unit
def test_core_system_status(client) -> None:
    """系统状态接口返回稳定字段 / System status endpoint returns stable fields."""
    resp = client.get("/api/core/v1/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "version" in data
    assert "capabilities" in data
    assert "system" in data


@pytest.mark.unit
def test_core_analysis_lifecycle(client, monkeypatch) -> None:
    """开始-查询-结束分析生命周期 / Start-result-stop lifecycle."""
    from ogscope.core.application import core_service

    async def _fake_start(**kwargs):  # noqa: ANN003
        _ = kwargs
        return {"success": True, "message": "started"}

    async def _fake_status():
        return {
            "running": True,
            "frame_count": 12,
            "fullsolve_count": 2,
            "last_result": {"status": "MATCH_FOUND", "ra_deg": 10.0, "dec_deg": 70.0},
            "last_error": "",
        }

    async def _fake_stop():
        return {"success": True, "message": "stopped"}

    monkeypatch.setattr(core_service.realtime_solve_service, "start", _fake_start)
    monkeypatch.setattr(core_service.realtime_solve_service, "get_status", _fake_status)
    monkeypatch.setattr(core_service.realtime_solve_service, "stop", _fake_stop)

    start = client.post("/api/core/v1/analysis/start", json={})
    assert start.status_code == 200
    assert start.json()["state"] == "running"

    result = client.get("/api/core/v1/analysis/result")
    assert result.status_code == 200
    body = result.json()
    assert body["state"] == "running"
    assert body["result"]["status"] == "MATCH_FOUND"

    stop = client.post("/api/core/v1/analysis/stop", json={})
    assert stop.status_code == 200
    assert stop.json()["state"] == "stopped"


@pytest.mark.unit
def test_core_camera_contract_endpoints(client, monkeypatch) -> None:
    """Core 相机接口可按契约返回 / Core camera endpoints respond by contract."""
    from ogscope.core.application import core_service
    from ogscope.web.api.core import routes as core_routes

    async def _fake_camera_status():
        return {
            "success": True,
            "connected": True,
            "streaming": True,
            "recording": False,
            "info": {"fps": 8},
            "runtime_overrides": {},
        }

    async def _fake_camera_tune(payload):  # noqa: ANN001
        return {
            "success": True,
            "message": "camera_tuned",
            "info": {"fps": payload.get("fps", 8)},
            "applied": payload,
        }

    async def _fake_stream_status():
        return {
            "success": True,
            "max_clients": 2,
            "active_clients": 1,
            "frame_fetch_timeout_ms": 20000,
            "target_preview_fps": 8,
        }

    async def _fake_list_video_files():
        return {"success": True, "files": [{"name": "VID_001.avi", "type": "video"}]}

    async def _fake_video_file_info(filename: str):
        return {"success": True, "file": {"filename": filename, "type": "video"}}

    async def _fake_preview(*, since_frame_id=None):  # noqa: ANN001
        _ = since_frame_id
        return Response(content=b"jpeg-bytes", media_type="image/jpeg")

    monkeypatch.setattr(
        core_service.core_contract_service, "get_camera_status", _fake_camera_status
    )
    monkeypatch.setattr(core_service.core_contract_service, "tune_camera", _fake_camera_tune)
    monkeypatch.setattr(
        core_service.core_contract_service, "get_stream_status", _fake_stream_status
    )
    monkeypatch.setattr(
        core_service.core_contract_service, "list_video_files", _fake_list_video_files
    )
    monkeypatch.setattr(
        core_service.core_contract_service,
        "get_video_file_info",
        _fake_video_file_info,
    )
    monkeypatch.setattr(core_routes.DebugCameraService, "get_preview", _fake_preview)

    status = client.get("/api/core/v1/camera/status")
    assert status.status_code == 200
    assert status.json()["connected"] is True

    tune = client.post("/api/core/v1/camera/tune", json={"fps": 10, "rotation": 180})
    assert tune.status_code == 200
    assert tune.json()["applied"]["fps"] == 10

    stream_status = client.get("/api/core/v1/camera/stream/status")
    assert stream_status.status_code == 200
    assert stream_status.json()["active_clients"] == 1

    videos = client.get("/api/core/v1/camera/videos")
    assert videos.status_code == 200
    assert len(videos.json()["files"]) == 1

    video = client.get("/api/core/v1/camera/videos/VID_001.avi")
    assert video.status_code == 200
    assert video.json()["file"]["filename"] == "VID_001.avi"

    preview = client.get("/api/core/v1/camera/preview")
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/jpeg"
