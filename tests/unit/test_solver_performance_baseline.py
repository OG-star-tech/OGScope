"""
解算性能基线测试 / Solver performance baseline tests
"""

from __future__ import annotations

import time

import cv2
import numpy as np
import pytest

from ogscope.algorithms.plate_solve import PlateSolver
from ogscope.algorithms.star_extract import StarExtractor


def _synthetic_frame(width: int = 640, height: int = 360, stars: int = 60) -> np.ndarray:
    """生成合成星空帧 / Generate synthetic star field frame."""
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    rng = np.random.default_rng(42)
    xs = rng.integers(0, width, size=stars)
    ys = rng.integers(0, height, size=stars)
    for x, y in zip(xs, ys):
        cv2.circle(frame, (int(x), int(y)), 1, (255, 255, 255), -1)
    return frame


@pytest.mark.unit
@pytest.mark.slow
def test_extract_and_solve_performance_baseline():
    """校验基础性能阈值 / Validate baseline performance threshold."""
    extractor = StarExtractor(max_stars=80)
    solver = PlateSolver(fov_deg=16.0)
    frame = _synthetic_frame()
    rounds = 40

    start = time.perf_counter()
    for _ in range(rounds):
        stars = extractor.extract(frame)
        solved = solver.solve(
            stars=stars,
            frame_shape=frame.shape,
            hint_ra_deg=12.0,
            hint_dec_deg=86.0,
            solve_source="full",
        )
        assert 0.0 <= solved.ra_deg <= 360.0
        assert -90.0 <= solved.dec_deg <= 90.0
    elapsed = time.perf_counter() - start
    avg_ms = (elapsed / rounds) * 1000.0

    # Pi Zero 上阈值会更高，这里以开发机回归检测为主 / Threshold is higher on Pi Zero; here we use dev-machine regression guard
    assert avg_ms < 35.0
