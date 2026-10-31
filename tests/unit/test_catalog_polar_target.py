"""Shared target contract regressions / 共享目标契约回归。"""

import asyncio
import copy
from unittest.mock import AsyncMock

import pytest

from ogscope.core.application.core_service import CoreContractService
from ogscope.domain.analysis.polar_guide import (
    attach_catalog_polar_guide,
    build_catalog_polar_guide,
)
from ogscope.web.api.analysis.services import AnalysisService


def solve():
    return {
        "status": "MATCH_FOUND",
        "ra_deg": 2.3,
        "dec_deg": 89.86,
        "roll_deg": 140.0,
        "fov_deg": 13.01,
        "observation_time_utc": "2026-10-13T12:00:00Z",
        "solve_overlay": {"frame_shape": [720, 1280]},
    }


def test_core_and_developer_return_identical_target_without_mutating_raw(monkeypatch):
    raw = solve()
    original = copy.deepcopy(raw)
    monkeypatch.setattr(
        "ogscope.core.application.core_service.realtime_solve_service.get_status",
        AsyncMock(
            return_value={
                "running": True,
                "last_result": attach_catalog_polar_guide(raw),
            }
        ),
    )
    core = asyncio.run(CoreContractService().get_analysis_result())["result"]
    dev = AnalysisService._build_polar_guide(
        None, raw, astronomy={"policy": "catalog_visual_v1"}
    )
    assert core["overlay_ext"]["polar_guide"] == dev
    assert dev["angular_sep_deg"] * 3600 == pytest.approx(504, abs=0.001)
    assert not any(dev["corrections"].values())
    assert raw == original


def test_rotation_changes_vector_but_not_target_distance():
    first = build_catalog_polar_guide(solve())
    second = build_catalog_polar_guide({**solve(), "roll_deg": 320})
    assert first["angular_sep_deg"] == second["angular_sep_deg"]
    for axis in ("dx", "dy"):
        assert first["image_offset_deg"][axis] == pytest.approx(
            -second["image_offset_deg"][axis]
        )


@pytest.mark.parametrize(
    "change", [{"fov_deg": 0}, {"dec_deg": float("nan")}, {"frame": "date"}]
)
def test_invalid_or_transformed_solve_has_no_catalog_target(change):
    assert build_catalog_polar_guide({**solve(), **change}) is None
