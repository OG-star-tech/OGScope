"""
分析 API 测试 / Analysis API tests
"""

from pathlib import Path

import cv2
import numpy as np
import pytest


def _build_star_image(path: Path) -> None:
    """生成测试星图 / Build test star image."""
    frame = np.zeros((320, 480, 3), dtype=np.uint8)
    points = [(120, 80), (200, 150), (330, 200), (400, 100), (250, 260)]
    for x, y in points:
        cv2.circle(frame, (x, y), 2, (255, 255, 255), -1)
    cv2.imwrite(str(path), frame)


def _build_test_video(path: Path) -> None:
    """生成测试视频 / Build test video."""
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, 8.0, (320, 240))
    if not writer.isOpened():
        raise RuntimeError("视频写入器初始化失败 / Failed to initialize video writer")
    for i in range(12):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        cx = 80 + (i * 4)
        cy = 90 + (i * 2)
        cv2.circle(frame, (cx, cy), 2, (255, 255, 255), -1)
        cv2.circle(frame, (200, 180), 2, (255, 255, 255), -1)
        writer.write(frame)
    writer.release()


@pytest.mark.unit
def test_analysis_upload_and_single_image_solve(
    client, temp_analysis_dir, mock_plate_solve, tmp_path: Path
):
    """测试上传与单图解算 / Test upload and single-image solve."""
    image_path = tmp_path / "stars.jpg"
    _build_star_image(image_path)
    with image_path.open("rb") as f:
        upload_resp = client.post(
            "/api/analysis/upload",
            files={"file": ("stars.jpg", f, "image/jpeg")},
        )
    assert upload_resp.status_code == 200
    assert upload_resp.json()["filename"] == "stars.jpg"

    list_resp = client.get("/api/analysis/uploads")
    assert list_resp.status_code == 200
    payload = list_resp.json()
    assert "upload_dir" in payload
    assert "files" in payload
    names = [f["filename"] for f in payload["files"]]
    assert "stars.jpg" in names

    file_resp = client.get(
        "/api/analysis/uploads/file", params={"filename": "stars.jpg"}
    )
    assert file_resp.status_code == 200
    assert len(file_resp.content) > 0

    solve_resp = client.post(
        "/api/analysis/solve/image",
        json={
            "input_name": "stars.jpg",
            "hint_ra_deg": 45.0,
            "hint_dec_deg": 70.0,
            "centroid": {"sigma": 2.5, "max_area": 400},
        },
    )
    assert solve_resp.status_code == 200
    solve_data = solve_resp.json()
    assert solve_data["success"] is True
    result = solve_data["result"]
    assert "ra_deg" in result
    assert "dec_deg" in result
    assert "status" in result


@pytest.mark.unit
def test_analysis_extract_preview(
    client, temp_analysis_dir, monkeypatch, tmp_path: Path
):
    """提星掩膜预览接口 / Extract preview endpoint smoke test."""
    image_path = tmp_path / "stars2.jpg"
    _build_star_image(image_path)
    with image_path.open("rb") as f:
        upload_resp = client.post(
            "/api/analysis/upload",
            files={"file": ("stars2.jpg", f, "image/jpeg")},
        )
    assert upload_resp.status_code == 200

    def _fake_preview(*_a: object, **_kw: object) -> dict:
        return {
            "success": True,
            "detected_stars": 5,
            "t_extract_ms": 10.0,
            "binary_mask_png_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
            "solve_width": 320,
            "solve_height": 480,
            "original_width": 320,
            "original_height": 480,
        }

    monkeypatch.setattr(
        "ogscope.web.api.analysis.services.centroid_extraction_preview",
        _fake_preview,
    )
    prev_resp = client.post(
        "/api/analysis/extract/preview",
        json={"input_name": "stars2.jpg", "max_image_side": 2048},
    )
    assert prev_resp.status_code == 200
    data = prev_resp.json()
    assert data.get("success") is True
    assert data.get("detected_stars") == 5
    assert data.get("t_extract_ms") == 10.0
    assert data.get("binary_mask_png_base64")


@pytest.mark.unit
def test_analysis_video_job(
    client, temp_analysis_dir, mock_plate_solve, tmp_path: Path
):
    """测试视频任务分析 / Test video job analysis."""
    video_path = tmp_path / "stars.mp4"
    _build_test_video(video_path)
    with video_path.open("rb") as f:
        upload_resp = client.post(
            "/api/analysis/upload",
            files={"file": ("stars.mp4", f, "video/mp4")},
        )
    assert upload_resp.status_code == 200

    job_resp = client.post(
        "/api/analysis/jobs",
        json={
            "input_name": "stars.mp4",
            "input_type": "video",
            "hint_ra_deg": 22.0,
            "hint_dec_deg": 84.0,
            "frame_step": 2,
            "max_frames": 6,
        },
    )
    assert job_resp.status_code == 200
    job_data = job_resp.json()
    assert job_data["status"] == "succeeded"

    status_resp = client.get(f"/api/analysis/jobs/{job_data['job_id']}")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "succeeded"

    result_resp = client.get(f"/api/analysis/jobs/{job_data['job_id']}/result")
    assert result_resp.status_code == 200
    result_data = result_resp.json()
    assert result_data["job_id"] == job_data["job_id"]
    assert len(result_data["results"]) > 0


@pytest.mark.unit
def test_analysis_list_presets_and_batch(
    client, temp_analysis_dir, mock_plate_solve, tmp_path: Path
):
    """预设列表与批量解算 / Presets list and batch solve."""
    image_path = tmp_path / "batch.jpg"
    _build_star_image(image_path)
    with image_path.open("rb") as f:
        up = client.post(
            "/api/analysis/upload",
            files={"file": ("batch.jpg", f, "image/jpeg")},
        )
    assert up.status_code == 200

    pr = client.get("/api/analysis/presets", params={"scope": "user"})
    assert pr.status_code == 200
    assert "presets" in pr.json()

    create = client.post(
        "/api/analysis/presets",
        json={
            "name": "test-preset",
            "params": {"fov_estimate": 16.0, "solve_timeout_ms": 8000},
        },
    )
    assert create.status_code == 200
    pid = create.json()["id"]

    batch = client.post(
        "/api/analysis/solve/batch",
        json={
            "input_name": "batch.jpg",
            "runs": [
                {"label": "A", "params": {"fov_estimate": 16.0}},
                {"label": "B", "params": {"fov_estimate": 15.0}},
            ],
        },
    )
    assert batch.status_code == 200
    bj = batch.json()
    assert bj["input_name"] == "batch.jpg"
    assert len(bj["results"]) == 2

    exp = client.post(
        "/api/analysis/experiments",
        json={
            "input_name": "batch.jpg",
            "preset_label": "A",
            "result_json": {"ok": True},
            "metrics": {"matches": 1},
        },
    )
    assert exp.status_code == 200

    el = client.get("/api/analysis/experiments", params={"page": 1, "page_size": 10})
    assert el.status_code == 200
    assert el.json()["total"] >= 1

    dl = client.delete(f"/api/analysis/presets/{pid}")
    assert dl.status_code == 200
