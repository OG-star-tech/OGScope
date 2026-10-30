"""Public routes must describe real capabilities / 公共路由只能描述真实能力。"""

import pytest


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/api/alignment/start"),
        ("post", "/api/alignment/stop"),
        ("get", "/api/alignment/status"),
    ],
)
def test_placeholder_mount_alignment_routes_are_not_exposed(client, method, path):
    response = getattr(client, method)(path)
    assert response.status_code == 404


def test_api_directory_does_not_advertise_placeholder_alignment(client):
    response = client.get("/api")
    assert response.status_code == 200
    assert "alignment" not in response.json()["endpoints"]


def test_api_directory_does_not_advertise_removed_system_routes(client):
    """目录只列出现行系统入口 / Advertise only the current system entry."""
    response = client.get("/api")
    endpoints = response.json()["endpoints"]
    assert endpoints["system"] == "/api/dev/system/"
    assert "system_legacy" not in endpoints
    assert "/api/system/" not in endpoints.values()
    assert client.get("/api/system/info").status_code == 404
