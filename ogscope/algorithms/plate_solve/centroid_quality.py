"""
质心几何质量过滤：局部过密与共线剔除 / Geometric centroid filtering (dense + collinear).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

_FLAG_DENSE = "DENSE_CLUSTER_REJECTED"
_FLAG_LINE = "LINE_CLUSTER_REJECTED"


def _level_params(level: int) -> dict[str, float | int]:
    """1=保守，5=激进 / 1=conservative, 5=aggressive."""
    lv = max(1, min(5, int(level)))
    return {
        "cell_px": max(18, 72 - lv * 11),
        "dense_min_points": max(4, 13 - lv * 2),
        "line_ransac_iters": 24 + lv * 10,
        "line_min_inliers": max(4, 11 - lv),
        "line_max_dist_px": 2.2 + (6 - lv) * 0.55,
        "line_min_span_frac": 0.10 + (5 - lv) * 0.025,
    }


def _reject_dense_clusters(
    xy: np.ndarray,
    h: int,
    w: int,
    *,
    cell_px: float,
    dense_min_points: int,
) -> tuple[np.ndarray, int, np.ndarray]:
    """网格密度：过密格及 3×3 邻域和超阈则整格丢弃 / Grid density rejection."""
    n = int(xy.shape[0])
    if n < dense_min_points:
        return xy, 0, np.empty((0, 2), dtype=np.float64)

    cols = max(1, int(math.ceil(w / cell_px)))
    rows = max(1, int(math.ceil(h / cell_px)))
    ix = np.clip((xy[:, 1] / cell_px).astype(np.int32), 0, cols - 1)
    iy = np.clip((xy[:, 0] / cell_px).astype(np.int32), 0, rows - 1)
    cell_id = iy * cols + ix

    counts = np.bincount(cell_id, minlength=rows * cols).reshape(rows, cols)

    bad = np.zeros_like(counts, dtype=bool)
    neigh_thresh = max(dense_min_points * 2, dense_min_points + 3)
    for r in range(rows):
        for c in range(cols):
            if counts[r, c] >= dense_min_points:
                bad[r, c] = True
                continue
            r0, r1 = max(0, r - 1), min(rows, r + 2)
            c0, c1 = max(0, c - 1), min(cols, c + 2)
            s = int(counts[r0:r1, c0:c1].sum())
            if s >= neigh_thresh:
                bad[r, c] = True

    bad_flat = bad[iy, ix]
    kept = xy[~bad_flat]
    removed_pts = xy[bad_flat]
    removed = int(n - kept.shape[0])
    return kept, removed, removed_pts


def _point_line_dist(points_yx: np.ndarray, p0: np.ndarray, p1: np.ndarray) -> np.ndarray:
    """点到线段距离（像素）/ Distance from points to segment."""
    # segment vector
    vx = p1[1] - p0[1]
    vy = p1[0] - p0[0]
    len2 = vx * vx + vy * vy
    if len2 < 1e-12:
        return np.hypot(points_yx[:, 1] - p0[1], points_yx[:, 0] - p0[0])
    t = ((points_yx[:, 1] - p0[1]) * vx + (points_yx[:, 0] - p0[0]) * vy) / len2
    t = np.clip(t, 0.0, 1.0)
    proj_x = p0[1] + t * vx
    proj_y = p0[0] + t * vy
    return np.hypot(points_yx[:, 1] - proj_x, points_yx[:, 0] - proj_y)


def _span_along_line(inlier_yx: np.ndarray) -> float:
    if inlier_yx.shape[0] < 2:
        return 0.0
    c = np.mean(inlier_yx, axis=0)
    _, _, vt = np.linalg.svd(inlier_yx - c, full_matrices=False)
    dire = vt[0]
    proj = (inlier_yx - c) @ dire
    return float(proj.max() - proj.min())


def _reject_collinear_ransac(
    xy: np.ndarray,
    h: int,
    w: int,
    *,
    iters: int,
    min_inliers: int,
    max_dist_px: float,
    min_span_frac: float,
) -> tuple[np.ndarray, int, np.ndarray]:
    """随机采样直线，剔除强共线簇 / RANSAC-style collinear rejection."""
    n = int(xy.shape[0])
    if n < min_inliers:
        return xy, 0, np.empty((0, 2), dtype=np.float64)

    min_span = min_span_frac * float(min(h, w))
    rng = np.random.default_rng(42)
    remain = xy.copy()
    total_removed = 0
    removed_chunks: list[np.ndarray] = []

    for _round in range(3):
        m = int(remain.shape[0])
        if m < min_inliers:
            break
        best_mask: np.ndarray | None = None
        best_count = 0

        for _ in range(iters):
            i, j = rng.integers(0, m, size=2)
            if i == j:
                continue
            p0 = remain[i]
            p1 = remain[j]
            d = _point_line_dist(remain, p0, p1)
            inl = d <= max_dist_px
            cnt = int(inl.sum())
            if cnt < min_inliers:
                continue
            span = _span_along_line(remain[inl])
            if span < min_span:
                continue
            if cnt > best_count:
                best_count = cnt
                best_mask = inl

        if best_mask is None or best_count < min_inliers:
            break

        span = _span_along_line(remain[best_mask])
        if span < min_span:
            break

        n_removed = int(best_mask.sum())
        removed_chunks.append(remain[best_mask].copy())
        remain = remain[~best_mask]
        total_removed += n_removed

    removed_pts = (
        np.concatenate(removed_chunks, axis=0)
        if removed_chunks
        else np.empty((0, 2), dtype=np.float64)
    )
    return remain, total_removed, removed_pts


def filter_centroids_yx(
    centroids_yx: np.ndarray,
    shape_hw: tuple[int, int],
    level: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    """过滤质心并返回指标与提示 / Filter centroids; returns metrics and hints.

    Args:
        centroids_yx: N×2 array, rows [y, x] in solve image pixels.
        shape_hw: (height, width) of solve image.
        level: 1 (mild) .. 5 (aggressive).

    Returns:
        Filtered centroids_yx, quality dict with flags, hints_zh_en, metrics.
    """
    arr = np.asarray(centroids_yx, dtype=np.float64)
    if arr.size == 0:
        return arr, _empty_quality(level, 0, 0)

    if arr.ndim != 2 or arr.shape[1] < 2:
        return arr, _empty_quality(level, int(arr.shape[0]), 0)

    h, w = int(shape_hw[0]), int(shape_hw[1])
    lv = max(1, min(5, int(level)))
    p = _level_params(lv)

    n0 = int(arr.shape[0])
    flags: list[str] = []
    hints: list[str] = []

    xy = arr[:, :2].copy()

    xy2, r_dense, dense_removed = _reject_dense_clusters(
        xy,
        h,
        w,
        cell_px=float(p["cell_px"]),
        dense_min_points=int(p["dense_min_points"]),
    )
    if r_dense > 0:
        flags.append(_FLAG_DENSE)
        hints.append(
            "局部区域星点过密已剔除（可能为树梢或亮斑）/ "
            "Rejected dense local region (trees or bright clutter)"
        )

    xy3, r_line, line_removed = _reject_collinear_ransac(
        xy2,
        h,
        w,
        iters=int(p["line_ransac_iters"]),
        min_inliers=int(p["line_min_inliers"]),
        max_dist_px=float(p["line_max_dist_px"]),
        min_span_frac=float(p["line_min_span_frac"]),
    )
    if r_line > 0:
        flags.append(_FLAG_LINE)
        hints.append(
            "共线星点已剔除（可能为电线）/ "
            "Rejected collinear detections (power lines)"
        )

    n1 = int(xy3.shape[0])
    rejected_pts = np.concatenate(
        [dense_removed, line_removed], axis=0
    ) if (dense_removed.size > 0 or line_removed.size > 0) else np.empty((0, 2), dtype=np.float64)
    quality: dict[str, Any] = {
        "level": lv,
        "flags": flags,
        "hints": hints,
        "metrics": {
            "input_count": n0,
            "output_count": n1,
            "removed_dense": r_dense,
            "removed_line": r_line,
        },
        "rejected_centroids_yx": rejected_pts.tolist(),
    }
    return xy3, quality


def _empty_quality(level: int, n_in: int, n_out: int) -> dict[str, Any]:
    return {
        "level": max(1, min(5, int(level))),
        "flags": [],
        "hints": [],
        "metrics": {
            "input_count": n_in,
            "output_count": n_out,
            "removed_dense": 0,
            "removed_line": 0,
        },
        "rejected_centroids_yx": [],
    }
