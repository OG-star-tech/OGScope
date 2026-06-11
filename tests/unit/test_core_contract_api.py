"""
Core 标准契约 API 测试 / Core standard contract API tests.
"""

from __future__ import annotations

import pytest


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
    assert "hardware_plane" in data
    assert "hardware_plane" in data
    assert "health_reasons" in data
    assert isinstance(data["health_reasons"], list)
    if data["health"] == "healthy":
        assert data["health_reasons"] == []
    else:
        assert len(data["health_reasons"]) >= 1


@pytest.mark.unit
def test_core_system_status_health_reasons() -> None:
    """health_reasons 反映相机与网络降级 / health_reasons reflect camera and network degradation."""
    from ogscope.core.application.core_service import CoreContractService

    reasons = CoreContractService._health_reasons(
        CoreContractService._normalize_camera_status(
            {"connected": False, "error": "Camera not initialized"},
        ),
        {"error": "wifi_not_configured"},
        network_in_health_scope=True,
    )
    assert "camera_not_connected" in reasons
    assert "network_wifi_not_configured" in reasons


@pytest.mark.unit
def test_core_system_status_health_reasons_ignore_delegated_network() -> None:
    """职责外网络不参与 health / Delegated network does not affect health."""
    from ogscope.core.application.core_service import CoreContractService

    reasons = CoreContractService._health_reasons(
        CoreContractService._normalize_camera_status({"connected": True}),
        {"error": "wifi_not_configured"},
        network_in_health_scope=False,
    )
    assert reasons == []


@pytest.mark.unit
def test_core_system_status_network_delegated_when_subordinate(monkeypatch) -> None:
    """subordinate 下 network 标记 delegated 且不降级 / Subordinate marks network delegated."""
    from ogscope.core.application.core_service import CoreContractService

    network = CoreContractService._build_network_status(
        {"role": "subordinate", "subordinate_mode": True},
        {"wifi_signal_dbm": -50.0, "wifi_quality": 88.0},
    )
    assert network["managed_by"] == "external"
    assert network["in_health_scope"] is False
    assert network["error"] is None
    assert network["signal_dbm"] == -50.0


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
        return {
            "success": True,
            "files": [
                {
                    "name": "VID_001.avi",
                    "type": "video",
                    "size": 1024,
                    "modified": "2026-01-01T00:00:00",
                }
            ],
        }

    async def _fake_video_file_info(filename: str):
        return {"success": True, "file": {"filename": filename, "type": "video"}}

    async def _fake_start_camera():
        return {"success": True, "message": "started"}

    async def _fake_stop_camera():
        return {"success": True, "message": "stopped"}

    monkeypatch.setattr(
        core_service.core_contract_service, "get_camera_status", _fake_camera_status
    )
    monkeypatch.setattr(core_service.core_contract_service, "tune_camera", _fake_camera_tune)
    monkeypatch.setattr(
        core_service.core_contract_service, "start_camera", _fake_start_camera
    )
    monkeypatch.setattr(core_service.core_contract_service, "stop_camera", _fake_stop_camera)
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

    status = client.get("/api/core/v1/camera/status")
    assert status.status_code == 200
    assert status.json()["connected"] is True

    tune = client.post("/api/core/v1/camera/tune", json={"fps": 10, "rotation": 180})
    assert tune.status_code == 200
    assert tune.json()["applied"]["fps"] == 10

    start = client.post("/api/core/v1/camera/start")
    assert start.status_code == 200
    assert start.json()["success"] is True

    stop = client.post("/api/core/v1/camera/stop")
    assert stop.status_code == 200
    assert stop.json()["success"] is True

    stream_status = client.get("/api/dev/debug/camera/stream/status")
    assert stream_status.status_code == 200
    assert stream_status.json()["active_clients"] == 1

    videos = client.get("/api/core/v1/camera/videos")
    assert videos.status_code == 200
    assert len(videos.json()["files"]) == 1

    video = client.get("/api/core/v1/camera/videos/VID_001.avi")
    assert video.status_code == 200
    assert video.json()["file"]["filename"] == "VID_001.avi"


@pytest.mark.unit
def test_core_video_info_rejects_invalid_filename(client) -> None:
    """视频详情接口应拒绝危险文件名 / Reject unsafe filename for video detail."""
    resp = client.get("/api/core/v1/camera/videos/..%5Csecret.txt")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "invalid filename"


@pytest.mark.unit
def test_docs_are_split_between_core_and_dev(client) -> None:
    """文档默认 core，dev 单独入口 / Docs split into core default and dev page."""
    docs = client.get("/docs")
    assert docs.status_code == 200
    assert "/openapi-core.json" in docs.text

    docs_dev = client.get("/docs/dev")
    assert docs_dev.status_code == 200
    assert "/openapi-dev.json" in docs_dev.text

    core_schema = client.get("/openapi-core.json")
    assert core_schema.status_code == 200
    core_paths = core_schema.json()["paths"]
    assert all(path.startswith("/api/core/v1/") for path in core_paths.keys())

    dev_schema = client.get("/openapi-dev.json")
    assert dev_schema.status_code == 200
    dev_paths = dev_schema.json()["paths"]
    assert any(path.startswith("/api/dev/analysis/") for path in dev_paths.keys())
    assert "/api/dev/debug/camera/stream" in dev_paths
    assert "/api/dev/debug/camera/stream/status" in dev_paths


@pytest.mark.unit
def test_core_openapi_contains_required_business_endpoints(client) -> None:
    """核心 REST 入口必须稳定存在 / Required core business endpoints remain stable."""
    resp = client.get("/openapi-core.json")
    assert resp.status_code == 200
    paths = set(resp.json()["paths"].keys())
    required = {
        "/api/core/v1/system/status",
        "/api/core/v1/analysis/start",
        "/api/core/v1/analysis/result",
        "/api/core/v1/analysis/stop",
        "/api/core/v1/camera/status",
    }
    assert required.issubset(paths)
    assert all(path.startswith("/api/core/v1/") for path in paths)
