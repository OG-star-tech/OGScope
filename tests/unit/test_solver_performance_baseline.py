"""
解算性能基线测试 / Solver performance baseline tests
"""

from __future__ import annotations

import time

import cv2
import numpy as np
import pytest

from ogscope.algorithms.star_extract import StarExtractor


def _synthetic_frame(
    width: int = 640, height: int = 360, stars: int = 60
) -> np.ndarray:
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
def test_star_extract_performance_baseline():
    """星点提取性能基线（不加载 Tetra 数据库）/ Star extraction baseline without Tetra DB."""
    extractor = StarExtractor(max_stars=80)
    frame = _synthetic_frame()
    rounds = 40

    start = time.perf_counter()
    for _ in range(rounds):
        stars = extractor.extract(frame)
        assert len(stars) >= 0
    elapsed = time.perf_counter() - start
    avg_ms = (elapsed / rounds) * 1000.0

    assert avg_ms < 35.0
