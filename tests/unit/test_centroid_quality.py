"""质心质量过滤单元测试 / Unit tests for centroid quality filter."""

from __future__ import annotations

import numpy as np
import pytest

from ogscope.algorithms.plate_solve.centroid_quality import filter_centroids_yx


@pytest.mark.unit
def test_filter_dense_cluster_removes_points_level5() -> None:
    """高等级应剔除局部密集格 / High level removes dense grid cell."""
    h, w = 200, 200
    pts = []
    # 密集 10 点于同一格 / Ten points in one cell
    for _ in range(10):
        pts.append([25.0, 25.0 + _ * 0.3])
    # 稀疏背景 / sparse background
    for i in range(20):
        pts.append([120.0 + (i % 5) * 8.0, 140.0 + (i // 5) * 9.0])
    cyx = np.asarray(pts, dtype=np.float64)
    out, q = filter_centroids_yx(cyx, (h, w), 5)
    assert q["metrics"]["removed_dense"] > 0
    assert out.shape[0] < cyx.shape[0]


@pytest.mark.unit
def test_filter_collinear_removes_line_level5() -> None:
    """共线点集应被剔除 / Collinear set is removed."""
    h, w = 320, 480
    pts = []
    # 水平线，x 在画幅内均匀分布，避免 clip 到同一格 / Stay inside frame for binning
    x0, x1 = 25.0, 455.0
    for i in range(15):
        pts.append([150.0, x0 + (x1 - x0) * i / 14.0])
    cyx = np.asarray(pts, dtype=np.float64)
    out, q = filter_centroids_yx(cyx, (h, w), 5)
    assert q["metrics"]["removed_line"] > 0 or "LINE_CLUSTER_REJECTED" in q["flags"]


@pytest.mark.unit
def test_level1_milder_than_level5_dense() -> None:
    """等级 1 剔除应不多于等级 5（密集场景）/ Level 1 removes no more than level 5."""
    h, w = 180, 180
    pts = [[20.0 + i * 0.2, 20.0] for i in range(8)]
    pts += [[100.0 + i * 15.0, 100.0] for i in range(10)]
    cyx = np.asarray(pts, dtype=np.float64)
    _, q1 = filter_centroids_yx(cyx, (h, w), 1)
    _, q5 = filter_centroids_yx(cyx, (h, w), 5)
    r1 = int(q1["metrics"]["removed_dense"]) + int(q1["metrics"]["removed_line"])
    r5 = int(q5["metrics"]["removed_dense"]) + int(q5["metrics"]["removed_line"])
    assert r5 >= r1
