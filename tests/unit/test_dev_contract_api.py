from __future__ import annotations

import pytest


@pytest.mark.unit
def test_dev_openapi_contains_dev_prefixed_paths(client) -> None:
    resp = client.get("/openapi-dev.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    assert paths
    assert all(path.startswith("/api/dev/") for path in paths.keys())


@pytest.mark.unit
def test_dev_system_info_available(client) -> None:
    resp = client.get("/api/dev/system/info")
    assert resp.status_code == 200
    body = resp.json()
    assert "platform" in body
    assert "cpu_usage" in body


@pytest.mark.unit
def test_dev_hardware_plane_status_available(client) -> None:
    resp = client.get("/api/dev/system/hardware-plane/status")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    assert "services" in payload["data"]
    assert "profile" in payload["data"]


@pytest.mark.unit
def test_dev_hardware_plane_sensor_read(client) -> None:
    resp = client.get("/api/dev/system/hardware-plane/sensors/gyroscope")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    assert payload["data"]["sensor"]["state"] in {
        "planned",
        "available",
        "degraded",
        "unavailable",
    }


@pytest.mark.unit
def test_dev_hardware_plane_metrics_include_profile(client) -> None:
    resp = client.get("/api/dev/system/hardware-plane/metrics")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    assert "profile" in payload["data"]


@pytest.mark.unit
def test_legacy_debug_path_not_exposed(client) -> None:
    resp = client.get("/api/debug/camera/status")
    assert resp.status_code in {404, 405}


@pytest.mark.unit
@pytest.mark.parametrize("accelerated", [False, True])
def test_stream_status_keeps_acceleration_diagnostics(client, monkeypatch, accelerated):
    """HTTP 响应不可丢失加速诊断，兼容旧指标 / Preserve acceleration diagnostics over HTTP and accept legacy metrics."""
    from ogscope.web.api.debug import routes

    async def status():
        data = {
            "success": True,
            "max_clients": 2,
            "active_clients": 1,
            "frame_fetch_timeout_ms": 20000,
            "target_preview_fps": 8,
        }
        if accelerated:
            data.update(
                preview_pipeline_enabled=True,
                hardware_encoder_error="codec unavailable",
            )
        return data

    monkeypatch.setattr(routes.core_contract_service, "get_stream_status", status)
    response = client.get("/api/dev/debug/camera/stream/status")
    assert response.status_code == 200
    body = response.json()
    assert body["preview_pipeline_enabled"] is accelerated
    assert body["hardware_encoder_error"] == (
        "codec unavailable" if accelerated else None
    )
