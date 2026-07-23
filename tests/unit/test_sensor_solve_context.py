"""Tests for sensor-assisted solve context / 传感器辅助解算上下文测试."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ogscope.algorithms.plate_solve.sensor_context import (
    attach_sensor_prediction,
    local_sidereal_time_deg,
)
from ogscope.web.api.models.schemas import AnalysisSolveImageRequest


def _solve_context(*, azimuth_deg: float = 0.0, altitude_deg: float = 90.0) -> dict:
    return {
        "observer": {
            "latitude_deg": 0.0,
            "longitude_deg": 0.0,
            "altitude_m": 0.0,
            "time_utc": "2000-01-01T12:00:00Z",
            "source": "test",
        },
        "orientation": {
            "azimuth_deg": azimuth_deg,
            "altitude_deg": altitude_deg,
            "heading_deg": azimuth_deg,
            "source": "test",
        },
        "quality": {
            "gps_valid": True,
            "time_valid": True,
            "heading_valid": True,
            "mount_valid": True,
        },
    }


def test_analysis_solve_image_accepts_solve_context() -> None:
    """旧请求兼容并接受新字段 / Old requests remain compatible and accept new field."""
    old_req = AnalysisSolveImageRequest.model_validate({"input_name": "stars.jpg"})
    assert old_req.solve_context is None

    req = AnalysisSolveImageRequest.model_validate(
        {"input_name": "stars.jpg", "solve_context": _solve_context()}
    )
    assert req.solve_context is not None
    assert req.solve_context.quality.gps_valid is True


def test_sensor_prediction_matches_zenith_at_equator() -> None:
    """赤道天顶预测应落在赤纬 0 附近 / Equator zenith predicts near Dec 0."""
    row = {"status": "MATCH_FOUND", "ra_deg": 0.0, "dec_deg": 0.0}
    context = _solve_context()
    expected_ra = local_sidereal_time_deg(
        0.0, datetime(2000, 1, 1, 12, tzinfo=timezone.utc)
    )
    row["ra_deg"] = expected_ra
    attach_sensor_prediction(row, context)

    pred = row["sensor_prediction"]
    assert pred["sensor_status"] == "matched"
    assert pred["predicted_dec_deg"] == pytest.approx(0.0, abs=1e-6)
    assert pred["predicted_ra_deg"] == pytest.approx(expected_ra, abs=1e-6)
    assert pred["sensor_delta_deg"] == pytest.approx(0.0, abs=1e-6)


def test_sensor_prediction_flags_mismatch() -> None:
    """偏差过大时标记 mismatch / Large delta only marks mismatch."""
    row = {"status": "MATCH_FOUND", "ra_deg": 180.0, "dec_deg": 0.0}
    attach_sensor_prediction(row, _solve_context(), threshold_deg=25.0)

    assert row["status"] == "MATCH_FOUND"
    assert row["sensor_prediction"]["sensor_status"] == "mismatch"
    assert row["sensor_prediction"]["sensor_delta_deg"] > 25.0


def test_sensor_prediction_unavailable_when_time_invalid() -> None:
    """传感器时间无效时保持 unavailable / Invalid sensor time stays unavailable."""
    context = _solve_context()
    context["quality"]["time_valid"] = False
    context["observer"]["time_utc"] = None
    row = {"status": "MATCH_FOUND", "ra_deg": 0.0, "dec_deg": 0.0}
    attach_sensor_prediction(row, context)

    assert row["sensor_prediction"]["sensor_status"] == "unavailable"
