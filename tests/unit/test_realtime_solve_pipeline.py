"""Core realtime solve pipeline tests / Core 实时解算管线测试。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import cv2
import numpy as np

from ogscope.algorithms.plate_solve.solver import SolveResult
from ogscope.core.realtime.service import RealtimeSolveService, SolveFrameSnapshot


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
