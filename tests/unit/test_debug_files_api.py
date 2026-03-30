"""
调试文件 API 的最小回归测试。
"""

import json

import pytest


@pytest.mark.unit
def test_debug_files_empty(client, temp_debug_dir):
    response = client.get("/api/debug/files")
    assert response.status_code == 200
    assert response.json() == {"files": []}


@pytest.mark.unit
def test_debug_files_list_and_info(client, temp_debug_dir):
    image_name = "IMG_20260101_000000.jpg"
    info_name = "IMG_20260101_000000.txt"

    (temp_debug_dir / image_name).write_bytes(b"fake-image-bytes")
    (temp_debug_dir / info_name).write_text(
        json.dumps({"exposure_us": 10000, "analogue_gain": 1.0}, ensure_ascii=False),
        encoding="utf-8",
    )

    files_resp = client.get("/api/debug/files")
    assert files_resp.status_code == 200
    files = files_resp.json()["files"]
    assert len(files) == 1
    assert files[0]["name"] == image_name
    assert files[0]["type"] == "image"

    info_resp = client.get(f"/api/debug/files/{image_name}/info")
    assert info_resp.status_code == 200
    info = info_resp.json()
    assert info["filename"] == image_name
    assert info["type"] == "image"
    assert info["exposure_us"] == 10000


@pytest.mark.unit
def test_debug_files_delete_removes_image_and_info(client, temp_debug_dir):
    image_name = "IMG_20260101_000001.jpg"
    info_name = "IMG_20260101_000001.txt"

    image_path = temp_debug_dir / image_name
    info_path = temp_debug_dir / info_name
    image_path.write_bytes(b"fake-image-bytes")
    info_path.write_text("{}", encoding="utf-8")

    delete_resp = client.delete(f"/api/debug/files/{image_name}")
    assert delete_resp.status_code == 200
    assert "message_key" in delete_resp.json()
    assert not image_path.exists()
    assert not info_path.exists()
