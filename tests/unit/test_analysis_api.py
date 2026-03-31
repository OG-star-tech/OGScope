"""
分析 API 测试 / Analysis API tests
"""

import json
import time
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


@pytest.mark.unit
def test_analysis_upload_file_info_sidecar(client, temp_analysis_dir, tmp_path: Path):
    """上传素材 info 接口合并 stem.txt / Upload info merges sidecar JSON."""
    image_path = tmp_path / "cap.jpg"
    _build_star_image(image_path)
    with image_path.open("rb") as f:
        up = client.post(
            "/api/analysis/upload",
            files={"file": ("cap.jpg", f, "image/jpeg")},
        )
    assert up.status_code == 200
    side = temp_analysis_dir / "uploads" / "cap.txt"
    side.write_text(
        '{"camera": {"exposure_us": 5000, "output_width": 640, "output_height": 480}}',
        encoding="utf-8",
    )
    info_resp = client.get("/api/analysis/uploads/cap.jpg/info")
    assert info_resp.status_code == 200
    data = info_resp.json()
    assert data.get("exposure_us") == 5000
    assert "640x480" in str(data.get("resolution", ""))


@pytest.mark.unit
def test_analysis_delete_upload_and_experiment(
    client, temp_analysis_dir, tmp_path: Path
):
    """删除素材与实验记录 / Delete upload and experiment."""
    image_path = tmp_path / "del.jpg"
    _build_star_image(image_path)
    with image_path.open("rb") as f:
        up = client.post(
            "/api/analysis/upload",
            files={"file": ("del.jpg", f, "image/jpeg")},
        )
    assert up.status_code == 200
    assert (temp_analysis_dir / "uploads" / "del.jpg").is_file()

    dr = client.delete("/api/analysis/uploads/del.jpg")
    assert dr.status_code == 200
    assert not (temp_analysis_dir / "uploads" / "del.jpg").is_file()

    exp = client.post(
        "/api/analysis/experiments",
        json={
            "input_name": "x.jpg",
            "preset_label": "t",
            "result_json": {"ok": True},
            "metrics": {"matches": 0},
        },
    )
    assert exp.status_code == 200
    eid = exp.json()["id"]
    er = client.delete(f"/api/analysis/experiments/{eid}")
    assert er.status_code == 200
    assert not (temp_analysis_dir / "experiments" / f"{eid}.json").is_file()


@pytest.mark.unit
def test_analysis_solve_video_frame_overlay_ext(
    client, temp_analysis_dir, mock_plate_solve, tmp_path: Path
):
    """单帧视频解算返回扩展叠加字段 / Frame solve returns overlay extension."""
    video_path = tmp_path / "frame_ext.mp4"
    _build_test_video(video_path)
    with video_path.open("rb") as f:
        up = client.post(
            "/api/analysis/upload",
            files={"file": ("frame_ext.mp4", f, "video/mp4")},
        )
    assert up.status_code == 200

    resp = client.post(
        "/api/analysis/solve/frame",
        json={
            "source": "file",
            "input_name": "frame_ext.mp4",
            "time_sec": 0.1,
            "overlay_topn_count": 2,
            "enable_polar_guide": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("success") is True
    row = data.get("result") or {}
    ext = row.get("overlay_ext") or {}
    labels = ext.get("labels_topn") or []
    assert isinstance(labels, list)
    assert len(labels) >= 1
    assert "name" in labels[0]
    guide = ext.get("polar_guide")
    assert isinstance(guide, dict)
    assert "delta_px" in guide


@pytest.mark.unit
def test_analysis_solve_video_frame_from_debug_capture(
    client, temp_analysis_dir, mock_plate_solve, monkeypatch, tmp_path: Path
):
    """调试录制目录的视频也可直接单帧解算 / Frame solve supports debug-capture videos."""
    video_path = tmp_path / "dev_captures" / "debug_cam.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    _build_test_video(video_path)
    monkeypatch.setattr("ogscope.web.api.analysis.services.Path.home", lambda: tmp_path)

    resp = client.post(
        "/api/analysis/solve/frame",
        json={
            "source": "file",
            "input_name": "debug_cam.mp4",
            "time_sec": 0.0,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("success") is True
    result = data.get("result") or {}
    assert "status" in result


@pytest.mark.unit
def test_analysis_solve_frame_upload_endpoint(
    client, temp_analysis_dir, mock_plate_solve, tmp_path: Path
):
    """浏览器提帧上传接口可解算 / Browser frame-upload endpoint solves frame."""
    image_path = tmp_path / "frame_upload.jpg"
    _build_star_image(image_path)
    payload = {
        "hint_ra_deg": 45.0,
        "hint_dec_deg": 75.0,
        "solve_profile": "balanced",
        "overlay_topn_count": 2,
        "enable_polar_guide": True,
    }
    with image_path.open("rb") as f:
        resp = client.post(
            "/api/analysis/solve/frame_upload",
            files={"file": ("frame.jpg", f, "image/jpeg")},
            data={"payload": json.dumps(payload)},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("success") is True
    row = data.get("result") or {}
    assert "status" in row
    ext = row.get("overlay_ext") or {}
    assert "labels_topn" in ext


@pytest.mark.unit
def test_analysis_realtime_gate_skips_by_interval(
    client, temp_analysis_dir, mock_plate_solve, tmp_path: Path
):
    """连续请求在最小间隔内会被跳过 / Consecutive calls are skipped by interval gate."""
    video_path = tmp_path / "gate_interval.mp4"
    _build_test_video(video_path)
    with video_path.open("rb") as f:
        up = client.post(
            "/api/analysis/upload",
            files={"file": ("gate_interval.mp4", f, "video/mp4")},
        )
    assert up.status_code == 200

    first = client.post(
        "/api/analysis/solve/frame",
        json={
            "source": "file",
            "input_name": "gate_interval.mp4",
            "time_sec": 0.1,
            "solve_interval_ms": 4000,
        },
    )
    assert first.status_code == 200
    assert first.json().get("gate_status") == "SOLVED"

    second = client.post(
        "/api/analysis/solve/frame",
        json={
            "source": "file",
            "input_name": "gate_interval.mp4",
            "time_sec": 0.1,
            "solve_interval_ms": 4000,
        },
    )
    assert second.status_code == 200
    data2 = second.json()
    assert data2.get("gate_status") == "SKIPPED_INTERVAL"
    assert isinstance(data2.get("next_allowed_in_ms"), int)


@pytest.mark.unit
def test_analysis_realtime_timeout_releases_gate(
    client, temp_analysis_dir, mock_plate_solve, monkeypatch, tmp_path: Path
):
    """超时后门禁释放，后续请求可恢复 / Timeout releases gate for following requests."""
    from ogscope.config import get_settings
    from ogscope.web.api.analysis.services import analysis_service

    image_path = tmp_path / "gate_timeout.jpg"
    _build_star_image(image_path)
    settings = get_settings()
    monkeypatch.setattr(settings, "star_analysis_request_timeout_ms", 80, raising=False)
    monkeypatch.setattr(settings, "star_analysis_min_interval_ms", 50, raising=False)
    monkeypatch.setattr(settings, "star_analysis_max_interval_ms", 20000, raising=False)
    gate = analysis_service._realtime_gate_states.get("file_upload")
    if gate is not None:
        gate.in_flight = False
        gate.last_finished_mono = 0.0

    def _slow(*_args, **_kwargs):
        time.sleep(0.2)
        return {
            "frame_index": 0,
            "status": "MATCH_FOUND",
            "ra_deg": 1.0,
            "dec_deg": 2.0,
            "solve_overlay": {},
        }

    monkeypatch.setattr(analysis_service, "_solve_bgr_to_row", _slow)
    with image_path.open("rb") as f:
        resp = client.post(
            "/api/analysis/solve/frame_upload",
            files={"file": ("frame.jpg", f, "image/jpeg")},
            data={"payload": json.dumps({"solve_interval_ms": 50})},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("gate_status") == "TIMEOUT_RELEASED"

    def _fast(*_args, **_kwargs):
        return {
            "frame_index": 0,
            "status": "MATCH_FOUND",
            "ra_deg": 1.0,
            "dec_deg": 2.0,
            "solve_overlay": {},
        }

    monkeypatch.setattr(analysis_service, "_solve_bgr_to_row", _fast)
    time.sleep(0.06)
    with image_path.open("rb") as f:
        resp2 = client.post(
            "/api/analysis/solve/frame_upload",
            files={"file": ("frame.jpg", f, "image/jpeg")},
            data={"payload": json.dumps({"solve_interval_ms": 50})},
        )
    assert resp2.status_code == 200
    assert resp2.json().get("gate_status") == "SOLVED"


@pytest.mark.unit
def test_analysis_camera_solve_skipped_when_recording_active(
    client, temp_analysis_dir, mock_plate_solve, monkeypatch
):
    """录制进行中时拒绝实时相机解算 / Reject camera solve when recording is active."""
    monkeypatch.setattr(
        "ogscope.web.api.debug.services.is_recording_active", lambda: True
    )
    resp = client.post(
        "/api/analysis/solve/frame",
        json={"source": "camera"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("gate_status") == "SKIPPED_BUSY"
    assert "recording" in str(data.get("gate_reason", ""))


@pytest.mark.unit
def test_analysis_replace_transcoded_video_updates_sidecar(
    client, temp_analysis_dir, tmp_path: Path
):
    """转码替换后删除旧 AVI 并更新侧车 / Replace transcoded video deletes old AVI and updates sidecar."""
    avi_path = tmp_path / "raw.avi"
    avi_path.write_bytes(b"AVI")
    mp4_path = tmp_path / "out.mp4"
    mp4_path.write_bytes(b"MP4")
    with avi_path.open("rb") as f:
        up_avi = client.post(
            "/api/analysis/upload",
            files={"file": ("raw.avi", f, "video/x-msvideo")},
        )
    assert up_avi.status_code == 200
    with mp4_path.open("rb") as f:
        up_mp4 = client.post(
            "/api/analysis/upload",
            files={"file": ("out.mp4", f, "video/mp4")},
        )
    assert up_mp4.status_code == 200

    side = temp_analysis_dir / "uploads" / "raw.txt"
    side.write_text(
        json.dumps(
            {
                "kind": "video",
                "media_file": "raw.avi",
                "extra": {"codec_fourcc": "MJPG", "container": "AVI"},
            }
        ),
        encoding="utf-8",
    )

    resp = client.post(
        "/api/analysis/uploads/replace_video",
        json={
            "old_filename": "raw.avi",
            "new_filename": "out.mp4",
            "duration_s": 3.2,
            "nominal_fps": 2.0,
            "codec_fourcc": "libx264",
            "container": "MP4",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("success") is True
    assert not (temp_analysis_dir / "uploads" / "raw.avi").exists()
    assert (temp_analysis_dir / "uploads" / "out.mp4").is_file()
    new_side = temp_analysis_dir / "uploads" / "out.txt"
    assert new_side.is_file()
    side_obj = json.loads(new_side.read_text(encoding="utf-8"))
    assert side_obj.get("media_file") == "out.mp4"
    extra = side_obj.get("extra") or {}
    assert extra.get("container") == "MP4"
