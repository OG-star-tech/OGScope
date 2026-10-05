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
    manager = SimpleNamespace(get_raw_frame=AsyncMock(return_value=(rgb, 7, 12.5)))
    monkeypatch.setattr("ogscope.web.camera_shared.get_camera_manager", lambda: manager)
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
