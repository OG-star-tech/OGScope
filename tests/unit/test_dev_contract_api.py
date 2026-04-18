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
def test_legacy_debug_path_not_exposed(client) -> None:
    resp = client.get("/api/debug/camera/status")
    assert resp.status_code in {404, 405}

