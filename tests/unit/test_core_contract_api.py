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
