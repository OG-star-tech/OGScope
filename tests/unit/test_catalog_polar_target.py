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


@pytest.mark.parametrize(
    "pole,dec,target", [("north", 89.0, 90.0), ("south", -89.0, -90.0)]
)
@pytest.mark.parametrize("roll", [0, 90, 180, 270])
def test_explicit_pole_preserves_one_degree_error_and_signed_image_vector(
    pole, dec, target, roll
):
    import math

    raw = {**solve(), "target_pole": pole, "dec_deg": dec, "roll_deg": roll}
    guide = build_catalog_polar_guide(raw)
    assert guide["target_kind"] == f"{pole}_celestial_pole"
    assert guide["target"]["dec_deg"] == target
    assert guide["angular_sep_deg"] == pytest.approx(1)
    assert guide["image_offset_deg"]["dx"] == pytest.approx(
        -(target - dec) * math.sin(math.radians(roll))
    )
    assert guide["image_offset_deg"]["dy"] == pytest.approx(
        -(target - dec) * math.cos(math.radians(roll))
    )
    assert guide["target_frame"] == "catalog_j2000"
    assert not any(guide["corrections"].values())


def test_legacy_target_does_not_follow_solve_hemisphere():
    guide = build_catalog_polar_guide({**solve(), "dec_deg": -89})
    assert guide["target_kind"] == "north_celestial_pole"
    assert guide["angular_sep_deg"] == pytest.approx(179)
    assert build_catalog_polar_guide({**solve(), "target_pole": "automatic"}) is None


def test_core_repeated_reads_preserve_south_target(monkeypatch):
    raw = attach_catalog_polar_guide({**solve(), "target_pole": "south", "dec_deg": -89})
    monkeypatch.setattr(
        "ogscope.core.application.core_service.realtime_solve_service.get_status",
        AsyncMock(return_value={"running": False, "last_result": raw}),
    )
    service = CoreContractService()
    first = asyncio.run(service.get_analysis_result())["result"]
    second = asyncio.run(service.get_analysis_result())["result"]
    assert first == second
    assert first["overlay_ext"]["polar_guide"]["target"]["dec_deg"] == -90
    assert (
        AnalysisService._build_polar_guide(None, raw, astronomy={"policy": "catalog_visual_v1"}, target_pole="south")
        == first["overlay_ext"]["polar_guide"]
    )


def test_running_session_rejects_target_change_without_stopping():
    from ogscope.core.realtime.service import RealtimeSolveService

    service = RealtimeSolveService()
    service.state.running = True
    service.state.session_id = "southern-session"
    service.state.target_pole = "south"
    result = asyncio.run(service.start(target_pole="north"))
    assert result["success"] is False
    assert result["error_code"] == "ANALYSIS_TARGET_CONFLICT"
    assert service.state.running
    assert service.state.target_pole == "south"


def test_core_request_accepts_only_explicit_supported_poles():
    from pydantic import ValidationError

    from ogscope.web.api.models.schemas import CoreStartAnalysisRequest

    assert CoreStartAnalysisRequest().target_pole == "north"
    assert CoreStartAnalysisRequest(target_pole="south").target_pole == "south"
    with pytest.raises(ValidationError):
        CoreStartAnalysisRequest(target_pole="automatic")
