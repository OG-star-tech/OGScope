"""Core realtime solve pipeline tests / Core 实时解算管线测试。"""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from ogscope.algorithms.plate_solve.solver import SolveResult
from ogscope.camera_optics import SC235HAI_16MM_F14_OPTICS
from ogscope.core.realtime import service as service_module
from ogscope.core.realtime.service import (
    RealtimeSolveService,
    SolveFrameSnapshot,
    camera_fov_deg,
)


def _solve_result(status: str, *, structural: bool = False) -> SolveResult:
    """构造最小解算结果 / Build a minimal solve result."""
    return SolveResult(
        ra_deg=12.0,
        dec_deg=80.0,
        detected_stars=8,
        solve_source="realtime",
        status=status,
        status_code=1 if status == "MATCH_FOUND" else 2,
        roll_deg=0.0,
        fov_deg=16.0,
        matches=6 if status == "MATCH_FOUND" else 0,
        prob=0.001,
        rmse_arcsec=7.5,
        t_solve_ms=4.0,
        t_extract_ms=2.0,
        t_preprocess_ms=1.0,
        centroid_quality={
            "scene": {"has_structural_evidence": structural},
        },
    )


def test_core_realtime_uses_authoritative_bgr_pipeline() -> None:
    """Core 与开发分析共用 Tetra 图像入口 / Core shares the Tetra image entry."""
    service = RealtimeSolveService()
    service.solver = MagicMock()
    frame = np.zeros((32, 48, 3), dtype=np.uint8)
    frame[0, 0] = [255, 0, 0]
    frame[0, 1] = [0, 0, 255]
    original = frame.copy()

    service._solve_frame_sync(frame)

    service.solver.solve_from_bgr_frame.assert_called_once()
    kwargs = service.solver.solve_from_bgr_frame.call_args.kwargs
    bgr = kwargs.pop("frame_bgr")
    np.testing.assert_array_equal(bgr[0, :2], [[0, 0, 255], [255, 0, 0]])
    np.testing.assert_array_equal(
        cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)[0, :2], [76, 29]
    )
    np.testing.assert_array_equal(frame, original)
    assert bgr is not frame
    assert kwargs == {
        "max_stars": service._max_stars,
        "hint_ra_deg": service._hint_ra,
        "hint_dec_deg": service._hint_dec,
        "solve_source": "realtime",
        "fov_estimate": service._fov_estimate,
        "fov_max_error": service._fov_max_error,
        "solve_timeout_ms": service._solve_timeout_ms,
    }
    service.solver.solve.assert_not_called()


def test_completed_realtime_frame_clears_transient_error() -> None:
    """新完成帧清除旧瞬时错误 / A completed frame clears an older transient error."""
    service = RealtimeSolveService()
    service.state.last_error = "temporary capture error"
    solved = MagicMock()
    solved.to_dict.return_value = {"status": "NO_MATCH"}
    solved.ra_deg = None
    solved.dec_deg = None

    service._apply_solve_result(solved)

    assert service.state.last_error == ""


def test_result_freezes_producing_pole_across_later_sessions() -> None:
    """结果保存产出时的天极 / Results retain the producing session's pole."""
    service = RealtimeSolveService()
    service.state.target_pole = "south"
    service._apply_solve_result(_solve_result("MATCH_FOUND"))
    southern_result = service.state.last_result
    service.state.target_pole = "north"
    service._apply_solve_result(_solve_result("MATCH_FOUND"))
    assert southern_result["target_pole"] == "south"
    assert service.state.last_result["target_pole"] == "north"


def test_analysis_event_carries_session_correlation() -> None:
    """结构化事件携带会话关联 ID / Structured events carry the session correlation ID."""
    service = RealtimeSolveService()
    service.state.session_id = "solve-123"
    service.state.started_mono = 1.0

    with patch("ogscope.core.realtime.service.logger") as mocked_logger:
        service._log_event("fullsolve_finished", status="NO_MATCH", detected_stars=2)

    template, payload_raw = mocked_logger.info.call_args.args
    payload = json.loads(payload_raw)
    assert template == "analysis_event {}"
    assert payload["session_id"] == "solve-123"
    assert payload["event"] == "fullsolve_finished"
    assert payload["status"] == "NO_MATCH"


def test_snapshot_policy_keeps_success_and_structural_failure() -> None:
    """成功与结构失败可检查，普通失败不额外编码 / Keep success and structural failures only."""
    assert RealtimeSolveService._should_retain_snapshot(_solve_result("MATCH_FOUND"))
    assert RealtimeSolveService._should_retain_snapshot(
        _solve_result("NO_MATCH", structural=True)
    )
    assert not RealtimeSolveService._should_retain_snapshot(_solve_result("NO_MATCH"))


def test_new_result_cannot_reuse_an_old_snapshot() -> None:
    """新结果必须覆盖旧图，避免错帧 / A new result must invalidate an old frame."""
    service = RealtimeSolveService()
    service.state.session_id = "session-a"
    snapshot = SolveFrameSnapshot(
        content=b"jpeg",
        session_id="session-a",
        frame_id=7,
        captured_at=1.0,
        width=64,
        height=48,
        encoder="test",
        encode_ms=1.5,
    )
    service._apply_solve_result(
        _solve_result("MATCH_FOUND"),
        frame_id=7,
        snapshot=snapshot,
        snapshot_attempted=True,
    )
    assert service.get_solve_frame_snapshot() == snapshot
    assert service.state.last_result is not None
    assert service.state.last_result["solve_frame"]["available"] is True

    service._apply_solve_result(_solve_result("NO_MATCH"), frame_id=8)
    assert service.get_solve_frame_snapshot() is None
    assert service.state.last_result["solve_frame"]["reason"] == "not_retained"


def test_acquisition_clock_step_invalidates_target_but_preserves_match(monkeypatch):
    """采集时钟跳变不伪造有效目标 / A capture-clock step cannot produce a valid target."""
    from ogscope.core.realtime import service as realtime

    service = RealtimeSolveService()
    service._astrometry_clock_anchor = (100.0, 50.0)
    monkeypatch.setattr(realtime.time, "time", lambda: 200.0)
    monkeypatch.setattr(realtime.time, "monotonic", lambda: 51.0)
    service._apply_solve_result(
        _solve_result("MATCH_FOUND"),
        capture_time={"observation_time_utc": "2026-10-31T00:00:00Z"},
    )
    assert service.state.last_result["status"] == "MATCH_FOUND"
    assert (
        service.state.last_result["astronomy"]["reason"] == "acquisition_clock_changed"
    )


# -- 视场估计：相机给出的视场 / The FOV estimate: the camera's field ------------------


def _camera_info(width: float | None) -> dict:
    """相机信息，带有效视场 / Camera info with an effective field."""
    if width is None:
        return {}
    return {"optics": {"effective_fov_deg": {"width": width, "height": 7.09}}}


@pytest.mark.parametrize(
    "info, fov",
    [
        (_camera_info(12.57), 12.57),
        (_camera_info(13), 13.0),
        ({}, None),
        ({"optics": None}, None),
        ({"optics": {"effective_fov_deg": {"width": "12.57"}}}, None),
        (_camera_info(0.0), None),
        (_camera_info(float("nan")), None),
        (_camera_info(True), None),
        (None, None),
    ],
)
def test_camera_fov_is_the_effective_width_or_nothing(info, fov) -> None:
    """只接受有效的数值宽度 / Only a valid numeric width counts."""
    assert camera_fov_deg(info) == fov


def test_the_fov_estimate_prefers_the_request_then_the_camera() -> None:
    """请求 > 相机 > 设置 / Request, then camera, then the setting."""
    service = RealtimeSolveService()
    settings_fov = service.solver.fov_deg
    assert service._fov_estimate_for(_camera_info(12.57)) == (12.57, "camera")
    assert service._fov_estimate_for({}) == (settings_fov, "settings")
    service._fov_estimate = 11.0
    assert service._fov_estimate_for(_camera_info(12.57)) == (11.0, "request")


def test_a_frame_is_solved_from_the_estimate_given() -> None:
    """给定估计传给解算器 / The given estimate reaches the solver."""
    service = RealtimeSolveService()
    service.solver = MagicMock()
    service._solve_frame_sync(np.zeros((8, 8, 3), dtype=np.uint8), 12.57)
    assert service.solver.solve_from_bgr_frame.call_args.kwargs["fov_estimate"] == 12.57


def test_the_result_says_where_the_estimate_came_from() -> None:
    """结果记录视场起点 / The result records the starting field."""
    service = RealtimeSolveService()
    service._apply_solve_result(
        _solve_result("MATCH_FOUND"), fov_estimate=(12.5654, "camera")
    )
    assert service.state.last_result["fov_estimate_deg"] == 12.565
    assert service.state.last_result["fov_estimate_source"] == "camera"


class _SC235HAICamera:
    """给出 SC235HAI 光学的相机 / A camera reporting the SC235HAI's optics."""

    is_capturing = True

    def get_camera_info(self) -> dict:
        optics = SC235HAI_16MM_F14_OPTICS.describe_capture(
            capture_width_px=1280, capture_height_px=720, sampling_mode="native"
        )
        return {"optics": optics}


class _Manager:
    """逐帧给出新帧 / Hands out a new frame each time."""

    def __init__(self) -> None:
        self.camera = _SC235HAICamera()
        self.frame_id = 0

    def get_camera_instance(self):
        return self.camera

    async def get_raw_frame(self):
        self.frame_id += 1
        return np.zeros((720, 1280, 3), dtype=np.uint8), self.frame_id, time.time()


@pytest.mark.asyncio
async def test_live_solves_start_from_the_fitted_sensors_field(monkeypatch) -> None:
    """实时解算从相机给出的视场开始，而非 13.01° 设置 /
    Live solves start from the camera's field, not the 13.01° setting."""
    service = RealtimeSolveService()
    service._analysis_interval_sec = 0.0
    service.state.running = True

    def solve(**kwargs):
        service.state.running = False
        return _solve_result("MATCH_FOUND")

    service.solver = MagicMock()
    service.solver.fov_deg = 13.01
    service.solver.solve_from_bgr_frame.side_effect = solve

    async def inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(service_module, "run_solver_job", inline)
    monkeypatch.setattr(service, "_should_retain_snapshot", lambda solved: False)

    await service._run_loop(_Manager())

    fov = service.solver.solve_from_bgr_frame.call_args.kwargs["fov_estimate"]
    assert fov == pytest.approx(12.57, abs=0.005)
    assert service.state.last_result["fov_estimate_source"] == "camera"
    assert service.state.last_result["fov_estimate_deg"] == pytest.approx(
        12.57, abs=0.005
    )
