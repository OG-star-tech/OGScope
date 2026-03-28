"""
分析管线集成测试 / Analysis pipeline integration tests
"""

from pathlib import Path

import cv2
import numpy as np
import pytest


def _make_frame(path: Path) -> None:
    """生成集成测试帧 / Generate integration test frame."""
    frame = np.zeros((300, 420, 3), dtype=np.uint8)
    for x, y in [(60, 70), (170, 110), (260, 180), (360, 90), (300, 240)]:
        cv2.circle(frame, (x, y), 2, (255, 255, 255), -1)
    cv2.imwrite(str(path), frame)


@pytest.mark.integration
def test_end_to_end_image_analysis(
    client, temp_analysis_dir, mock_plate_solve, tmp_path: Path
):
    """验证上传与单图解算全链路 / Validate upload to single-image solving."""
    image = tmp_path / "integration_stars.jpg"
    _make_frame(image)
    with image.open("rb") as f:
        resp_upload = client.post(
            "/api/analysis/upload",
            files={"file": ("integration_stars.jpg", f, "image/jpeg")},
        )
    assert resp_upload.status_code == 200

    resp_solve = client.post(
        "/api/analysis/solve/image",
        params={"input_name": "integration_stars.jpg", "hint_ra_deg": 31.0, "hint_dec_deg": 88.0},
    )
    assert resp_solve.status_code == 200
    payload = resp_solve.json()
    assert payload["success"] is True
    assert payload["result"]["solve_source"] == "full"
