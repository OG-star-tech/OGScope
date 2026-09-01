"""Core realtime solve pipeline tests / Core 实时解算管线测试。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import numpy as np

from ogscope.core.realtime.service import RealtimeSolveService


def test_core_realtime_uses_authoritative_bgr_pipeline() -> None:
    """Core 与开发分析共用 Tetra 图像入口 / Core shares the Tetra image entry."""
    service = RealtimeSolveService()
    service.solver = MagicMock()
    frame = np.zeros((32, 48, 3), dtype=np.uint8)

    service._solve_frame_sync(frame)

    service.solver.solve_from_bgr_frame.assert_called_once_with(
        frame_bgr=frame,
        max_stars=service._max_stars,
        hint_ra_deg=service._hint_ra,
        hint_dec_deg=service._hint_dec,
        solve_source="realtime",
        fov_estimate=service._fov_estimate,
        fov_max_error=service._fov_max_error,
        solve_timeout_ms=service._solve_timeout_ms,
    )
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
