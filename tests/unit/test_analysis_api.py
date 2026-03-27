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
def test_analysis_upload_and_single_image_solve(client, temp_analysis_dir, temp_catalog_dir, tmp_path: Path):
    """测试上传与单图解算 / Test upload and single-image solve."""
    client.post("/api/catalog/download", json={"source": "seed"})
    client.post("/api/catalog/build-index", json={"magnitude_limit": 8.5})

    image_path = tmp_path / "stars.jpg"
    _build_star_image(image_path)
    with image_path.open("rb") as f:
        upload_resp = client.post(
            "/api/analysis/upload",
            files={"file": ("stars.jpg", f, "image/jpeg")},
        )
    assert upload_resp.status_code == 200
    assert upload_resp.json()["filename"] == "stars.jpg"

    solve_resp = client.post(
        "/api/analysis/solve/image",
        params={"input_name": "stars.jpg", "hint_ra_deg": 45.0, "hint_dec_deg": 70.0},
    )
    assert solve_resp.status_code == 200
    solve_data = solve_resp.json()
    assert solve_data["success"] is True
    result = solve_data["result"]
    assert "ra_deg" in result
    assert "dec_deg" in result
    assert "confidence" in result


@pytest.mark.unit
def test_analysis_video_job(client, temp_analysis_dir, temp_catalog_dir, tmp_path: Path):
    """测试视频任务分析 / Test video job analysis."""
    client.post("/api/catalog/download", json={"source": "seed"})
    client.post("/api/catalog/build-index", json={"magnitude_limit": 8.5})

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
