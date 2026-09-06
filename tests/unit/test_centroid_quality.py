"""质心质量过滤单元测试 / Unit tests for centroid quality filter."""

from __future__ import annotations

import numpy as np
import pytest

from ogscope.algorithms.plate_solve.centroid_quality import filter_centroids_yx


@pytest.mark.unit
def test_dense_cluster_without_image_evidence_is_not_removed() -> None:
    """密度本身不能判定遮挡 / Density alone must not classify obstruction."""
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
    assert q["metrics"]["dense_candidates"] > 0
    assert q["metrics"]["removed_dense"] == 0
    assert np.array_equal(out, cyx)


@pytest.mark.unit
def test_dense_cluster_with_image_evidence_is_removed() -> None:
    """局部密度与结构证据重合时才剔除 / Reject density only with structural evidence."""
    h, w = 200, 200
    cyx = np.asarray(
        [[25.0, 25.0 + i * 0.3] for i in range(10)]
        + [[120.0 + (i % 5) * 8.0, 140.0 + (i // 5) * 9.0] for i in range(20)],
        dtype=np.float64,
    )
    evidence = np.zeros((h, w), dtype=bool)
    evidence[15:40, 15:45] = True
    out, q = filter_centroids_yx(
        cyx,
        (h, w),
        5,
        evidence_mask=evidence,
    )
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
    evidence = np.ones((h, w), dtype=bool)
    out, q = filter_centroids_yx(cyx, (h, w), 5, evidence_mask=evidence)
    assert q["metrics"]["removed_line"] > 0 or "LINE_CLUSTER_REJECTED" in q["flags"]


@pytest.mark.unit
def test_level1_milder_than_level5_dense() -> None:
    """等级 1 剔除应不多于等级 5（密集场景）/ Level 1 removes no more than level 5."""
    h, w = 180, 180
    pts = [[20.0 + i * 0.2, 20.0] for i in range(8)]
    pts += [[100.0 + i * 15.0, 100.0] for i in range(10)]
    cyx = np.asarray(pts, dtype=np.float64)
    evidence = np.ones((h, w), dtype=bool)
    _, q1 = filter_centroids_yx(cyx, (h, w), 1, evidence_mask=evidence)
    _, q5 = filter_centroids_yx(cyx, (h, w), 5, evidence_mask=evidence)
    r1 = int(q1["metrics"]["removed_dense"]) + int(q1["metrics"]["removed_line"])
    r5 = int(q5["metrics"]["removed_dense"]) + int(q5["metrics"]["removed_line"])
    assert r5 >= r1


@pytest.mark.unit
def test_filter_caps_rejection_and_keeps_at_least_four() -> None:
    """过滤达到上限时保守放行 / Filtering fails open at its rejection cap."""
    h, w = 120, 200
    cyx = np.asarray([[60.0, 10.0 + i * 4.0] for i in range(20)])
    evidence = np.ones((h, w), dtype=bool)
    out, q = filter_centroids_yx(
        cyx,
        (h, w),
        5,
        evidence_mask=evidence,
        max_rejected_fraction=0.25,
    )
    assert out.shape[0] == 15
    assert q["metrics"]["filter_limited"] is True
    assert "CENTROID_FILTER_LIMITED" in q["flags"]


@pytest.mark.unit
def test_limited_filter_balances_bright_and_dark_evidence_regions() -> None:
    """达到上限时亮区不能独占额度 / Bright evidence cannot monopolize a limited cap."""
    h, w = 200, 200
    bright_cluster = [[25.0 + i * 0.2, 25.0] for i in range(10)]
    dark_cluster = [[165.0 + i * 0.2, 165.0] for i in range(10)]
    cyx = np.asarray(bright_cluster + dark_cluster, dtype=np.float64)
    evidence = np.zeros((h, w), dtype=bool)
    evidence[15:45, 15:45] = True
    evidence[155:190, 155:190] = True
    labels = np.zeros((h, w), dtype=np.uint16)
    labels[15:45, 15:45] = 1
    labels[155:190, 155:190] = 2

    out, quality = filter_centroids_yx(
        cyx,
        (h, w),
        5,
        evidence_mask=evidence,
        evidence_region_labels=labels,
        max_rejected_fraction=0.20,
    )

    rejected = np.asarray(quality["rejected_centroids_yx"], dtype=np.float64)
    assert out.shape[0] == 16
    assert np.any(rejected[:, 0] < 50.0)
    assert np.any(rejected[:, 0] > 150.0)
    assert quality["metrics"]["evidence_regions_considered"] == 2
    assert quality["metrics"]["evidence_regions_rejected"] == 2
    assert quality["metrics"]["rejection_balanced"] is True
