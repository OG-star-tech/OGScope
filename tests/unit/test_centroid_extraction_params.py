"""V4L2 后端专用提星 sigma 选择测试 / Tests for backend-specific centroid sigma selection."""

from __future__ import annotations

import pytest

from ogscope.algorithms.plate_solve.solver import CentroidExtractionParams
from ogscope.config import Settings


@pytest.mark.unit
def test_from_settings_uses_v4l2_sigma_for_v4l2_backend() -> None:
    settings = Settings(
        camera_type="v4l2",
        solver_centroid_sigma=2.5,
        solver_centroid_sigma_v4l2=1.9,
    )
    params = CentroidExtractionParams.from_settings(settings)
    assert params.sigma == pytest.approx(1.9)


@pytest.mark.unit
def test_from_settings_uses_default_sigma_for_picamera2_backend() -> None:
    settings = Settings(
        camera_type="imx327_mipi",
        solver_centroid_sigma=2.5,
        solver_centroid_sigma_v4l2=1.9,
    )
    params = CentroidExtractionParams.from_settings(settings)
    assert params.sigma == pytest.approx(2.5)


@pytest.mark.unit
def test_from_settings_normalizes_v4l2_aliases() -> None:
    for alias in ("v4l2_raw", "linuxpy_v4l2", "v4l2_linuxpy"):
        settings = Settings(
            camera_type=alias,
            solver_centroid_sigma=2.5,
            solver_centroid_sigma_v4l2=1.9,
        )
        params = CentroidExtractionParams.from_settings(settings)
        assert params.sigma == pytest.approx(1.9), f"alias={alias}"
