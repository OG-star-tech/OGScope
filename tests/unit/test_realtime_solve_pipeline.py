"""Core realtime solve pipeline tests / Core 实时解算管线测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

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
