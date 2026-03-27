"""
星表 API 测试 / Catalog API tests
"""

import pytest


@pytest.mark.unit
def test_catalog_download_build_and_status(client, temp_catalog_dir):
    """测试星表下载、建索引和状态查询 / Test catalog download, build index and status."""
    download_resp = client.post(
        "/api/catalog/download",
        json={"source": "seed", "magnitude_limit": 8.5},
    )
    assert download_resp.status_code == 200
    download_data = download_resp.json()
    assert download_data["success"] is True
    assert "path" in download_data

    build_resp = client.post(
        "/api/catalog/build-index",
        json={"magnitude_limit": 8.5, "ra_bin_size_deg": 30.0},
    )
    assert build_resp.status_code == 200
    build_data = build_resp.json()
    assert build_data["success"] is True
    assert build_data["record_count"] > 0
    assert build_data["bucket_count"] > 0

    status_resp = client.get("/api/catalog/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["ready"] is True
    assert status_data["status"] == "ready"


@pytest.mark.unit
def test_catalog_star_crud(client, temp_catalog_dir):
    """测试星点 CRUD 接口 / Test catalog star CRUD APIs."""
    create_resp = client.post(
        "/api/catalog/stars",
        json={
            "source_id": "custom_star_001",
            "ra": 123.4,
            "dec": 45.6,
            "pmra": 0.3,
            "pmdec": -0.2,
            "phot_g_mean_mag": 6.7,
        },
    )
    assert create_resp.status_code == 200
    create_data = create_resp.json()
    assert create_data["source_id"] == "custom_star_001"

    get_resp = client.get("/api/catalog/stars/custom_star_001")
    assert get_resp.status_code == 200
    assert get_resp.json()["phot_g_mean_mag"] == 6.7

    list_resp = client.get("/api/catalog/stars", params={"source_query": "custom_star"})
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] >= 1

    update_resp = client.put(
        "/api/catalog/stars/custom_star_001",
        json={
            "source_id": "custom_star_001",
            "ra": 124.5,
            "dec": 44.4,
            "pmra": 0.4,
            "pmdec": -0.1,
            "phot_g_mean_mag": 5.8,
        },
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["phot_g_mean_mag"] == 5.8

    delete_resp = client.delete("/api/catalog/stars/custom_star_001")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["success"] is True
