"""相机 RGB 与文件 BGR 分析契约 / Camera RGB and decoded file BGR analysis contracts."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import cv2
import numpy as np
import pytest

from ogscope.web.api.analysis.services import analysis_service
from ogscope.web.api.models.schemas import (
    AnalysisSolveImageRequest,
    AnalysisSolveVideoFrameRequest,
)


def _rgb_frame():
    """用红蓝非对称输入检测色序 / Use asymmetric red and blue to detect channel order."""
    frame = np.zeros((16, 32, 3), dtype=np.uint8)
    frame[:, :16] = [255, 0, 0]
    frame[:, 16:] = [0, 0, 255]
    return frame


@pytest.fixture
def color_solver(monkeypatch, temp_analysis_dir):
    """隔离解算门禁，记录分析输入 / Isolate the solve gate and record analysis input."""
    monkeypatch.setattr(
        type(analysis_service), "_try_enter_realtime_gate", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(type(analysis_service), "_leave_realtime_gate", AsyncMock())
    monkeypatch.setattr(type(analysis_service), "_attach_overlay_ext", MagicMock())
    solver = MagicMock(return_value={"status": "MATCH_FOUND", "frame_index": 0})
    monkeypatch.setattr(type(analysis_service), "_solve_bgr_to_row", solver)
    return solver


@pytest.mark.unit
@pytest.mark.asyncio
async def test_debug_camera_analysis_converts_rgb_and_preserves_snapshot(
    monkeypatch, color_solver
):
    """相机分析使用 BGR 副本，精确快照保留 RGB / Solve BGR while the exact snapshot keeps RGB."""
    from ogscope.core.realtime import realtime_solve_service

    monkeypatch.setattr(realtime_solve_service.state, "running", False)
    monkeypatch.setattr(
        "ogscope.web.api.debug.services.is_recording_active", lambda: False
    )
    rgb = _rgb_frame()
    original = rgb.copy()
    manager = SimpleNamespace(
        get_raw_frame=AsyncMock(return_value=(rgb, 7, 12.5)),
        get_camera_instance=lambda: None,
        acquire_analysis_consumer=AsyncMock(),
        release_analysis_consumer=AsyncMock(),
    )
    monkeypatch.setattr(
        "ogscope.application.camera.get_camera_capture", lambda: manager
    )
    snapshot = MagicMock(return_value={"available": True, "frame_id": 7})
    monkeypatch.setattr(
        type(analysis_service), "_encode_debug_solve_snapshot", snapshot
    )

    result = await analysis_service.solve_video_frame(
        AnalysisSolveVideoFrameRequest(source="camera")
    )

    bgr = color_solver.call_args.args[0]
    np.testing.assert_array_equal(bgr, rgb[..., ::-1])
    np.testing.assert_array_equal(
        cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)[0, [0, 16]], [76, 29]
    )
    np.testing.assert_array_equal(rgb, original)
    assert bgr is not rgb
    assert snapshot.call_args.args[0] is rgb
    assert snapshot.call_args.args[1] == 7
    assert result["frame_id"] == 7
    assert result["frame_ts"] == 12.5
    manager.acquire_analysis_consumer.assert_awaited_once()
    manager.release_analysis_consumer.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uploaded_frame_analysis_keeps_decoded_bgr(color_solver):
    """上传解码已经是 BGR，无二次交换 / Uploaded decoding is BGR and needs no second swap."""
    bgr = _rgb_frame()[..., ::-1].copy()
    ok, encoded = cv2.imencode(".png", bgr)
    assert ok

    result = await analysis_service.solve_uploaded_frame(
        image_bytes=encoded.tobytes(),
        solve_params=AnalysisSolveImageRequest(input_name="colors.png"),
    )

    assert result["gate_status"] == "SOLVED"
    np.testing.assert_array_equal(color_solver.call_args.args[0], bgr)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_video_file_analysis_keeps_decoded_bgr(monkeypatch, color_solver):
    """视频解码保持 BGR 契约 / Video decoding keeps the BGR contract."""
    bgr = _rgb_frame()[..., ::-1].copy()
    capture = MagicMock()
    capture.isOpened.return_value = True
    capture.read.return_value = (True, bgr)
    monkeypatch.setattr(cv2, "VideoCapture", lambda _path: capture)
    monkeypatch.setattr(
        type(analysis_service), "_resolve_frame_source_path", lambda self, name: name
    )

    result = await analysis_service.solve_video_frame(
        AnalysisSolveVideoFrameRequest(source="file", input_name="colors.mp4")
    )

    assert result["gate_status"] == "SOLVED"
    assert color_solver.call_args.args[0] is bgr
    capture.release.assert_called_once()


@pytest.mark.asyncio
async def test_lab_preparation_failure_never_calls_solver_and_releases_gate(
    monkeypatch, color_solver
):
    """No sky failure is produced before capture is ready / 相机就绪前不能生成星图失败。"""
    from ogscope.core.realtime import realtime_solve_service

    monkeypatch.setattr(realtime_solve_service.state, "running", False)
    monkeypatch.setattr(
        "ogscope.web.api.debug.services.is_recording_active", lambda: False
    )
    manager = SimpleNamespace(
        acquire_analysis_consumer=AsyncMock(), release_analysis_consumer=AsyncMock()
    )
    monkeypatch.setattr(
        "ogscope.application.camera.get_camera_capture", lambda: manager
    )
    monkeypatch.setattr(
        "ogscope.domain.camera.readiness.wait_capture_ready",
        AsyncMock(side_effect=RuntimeError("CAMERA_NOT_READY")),
    )
    with pytest.raises(RuntimeError, match="CAMERA_NOT_READY"):
        await analysis_service.solve_video_frame(
            AnalysisSolveVideoFrameRequest(source="camera")
        )
    color_solver.assert_not_called()
    manager.release_analysis_consumer.assert_awaited_once()
    analysis_service._leave_realtime_gate.assert_awaited_once_with("camera")


@pytest.mark.asyncio
@pytest.mark.parametrize("clock_step", [0.0, 10.0])
async def test_debug_exposure_metadata_is_frozen_before_slow_solve(
    monkeypatch, color_solver, clock_step
):
    """解算期间的下一次曝光不得改变当前帧时刻 / Later exposure settings cannot retime the solved frame."""
    from ogscope.core.realtime import realtime_solve_service
    from ogscope.web.api.analysis import services

    original_time = services.time.time
    elapsed_step = [0.0]
    monkeypatch.setattr(
        services.time, "time", lambda: original_time() + elapsed_step[0]
    )

    monkeypatch.setattr(realtime_solve_service.state, "running", False)
    monkeypatch.setattr(
        "ogscope.web.api.debug.services.is_recording_active", lambda: False
    )
    info = {"actual_exposure_us": 1_000_000}
    camera = SimpleNamespace(get_camera_info=lambda: info)
    manager = SimpleNamespace(
        get_raw_frame=AsyncMock(return_value=(_rgb_frame(), 7, 1_793_404_800.0)),
        get_camera_instance=lambda: camera,
        acquire_analysis_consumer=AsyncMock(),
        release_analysis_consumer=AsyncMock(),
    )
    monkeypatch.setattr("ogscope.web.camera_shared.get_camera_manager", lambda: manager)
    monkeypatch.setattr(
        "ogscope.domain.camera.readiness.wait_capture_ready", AsyncMock(return_value={})
    )

    def solve_while_camera_advances(*args, **kwargs):
        info["actual_exposure_us"] = 9_000_000
        elapsed_step[0] = clock_step
        return {"status": "NO_MATCH"}

    color_solver.side_effect = solve_while_camera_advances
    result = await analysis_service.solve_video_frame(
        AnalysisSolveVideoFrameRequest(source="camera")
    )
    assert result["result"]["capture_exposure_us"] == 1_000_000
    assert result["result"]["observation_time_utc"] == "2026-10-30T23:59:59.500000Z"
    assert result["result"].get("observation_time_error") == (
        "acquisition_clock_changed" if clock_step else None
    )
