"""
质心几何质量过滤：局部过密与共线剔除 / Geometric centroid filtering (dense + collinear).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

_FLAG_DENSE = "DENSE_CLUSTER_REJECTED"
_FLAG_LINE = "LINE_CLUSTER_REJECTED"
_FLAG_LIMITED = "CENTROID_FILTER_LIMITED"


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


def _dense_cluster_mask(
    xy: np.ndarray,
    h: int,
    w: int,
    *,
    cell_px: float,
    dense_min_points: int,
) -> np.ndarray:
    """返回局部过密候选；密度本身不负责剔除 / Mark dense candidates without rejecting."""
    n = int(xy.shape[0])
    if n < dense_min_points:
        return np.zeros(n, dtype=bool)

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

    return bad[iy, ix]


def _point_line_dist(
    points_yx: np.ndarray, p0: np.ndarray, p1: np.ndarray
) -> np.ndarray:
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


def _collinear_cluster_mask(
    xy: np.ndarray,
    h: int,
    w: int,
    *,
    iters: int,
    min_inliers: int,
    max_dist_px: float,
    min_span_frac: float,
) -> np.ndarray:
    """随机采样并标记强共线簇 / Mark strong collinear clusters with RANSAC."""
    n = int(xy.shape[0])
    if n < min_inliers:
        return np.zeros(n, dtype=bool)

    min_span = min_span_frac * float(min(h, w))
    rng = np.random.default_rng(42)
    remain_idx = np.arange(n, dtype=np.int32)
    rejected = np.zeros(n, dtype=bool)

    for _round in range(3):
        remain = xy[remain_idx]
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

        rejected[remain_idx[best_mask]] = True
        remain_idx = remain_idx[~best_mask]

    return rejected


def _points_on_evidence_mask(
    xy: np.ndarray,
    evidence_mask: np.ndarray | None,
    shape_hw: tuple[int, int],
) -> np.ndarray:
    """采样候选点所在的结构证据 / Sample structural evidence at candidates."""
    n = int(xy.shape[0])
    if evidence_mask is None:
        return np.zeros(n, dtype=bool)
    mask = np.asarray(evidence_mask, dtype=bool)
    h, w = int(shape_hw[0]), int(shape_hw[1])
    if mask.shape != (h, w):
        raise ValueError("evidence_mask shape must match shape_hw")
    iy = np.clip(np.floor(xy[:, 0]).astype(np.int32), 0, h - 1)
    ix = np.clip(np.floor(xy[:, 1]).astype(np.int32), 0, w - 1)
    return mask[iy, ix]


def filter_centroids_yx(
    centroids_yx: np.ndarray,
    shape_hw: tuple[int, int],
    level: int,
    *,
    evidence_mask: np.ndarray | None = None,
    max_rejected_fraction: float = 0.35,
) -> tuple[np.ndarray, dict[str, Any]]:
    """过滤质心并返回指标与提示 / Filter centroids; returns metrics and hints.

    Args:
        centroids_yx: N×2 array, rows [y, x] in solve image pixels.
        shape_hw: (height, width) of solve image.
        level: 1 (mild) .. 5 (aggressive).
        evidence_mask: Structural evidence from the source image. Dense or linear
            geometry is only rejected where this independent evidence is present.
        max_rejected_fraction: Fail-open cap for one fallback attempt.

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

    dense_candidates = _dense_cluster_mask(
        xy,
        h,
        w,
        cell_px=float(p["cell_px"]),
        dense_min_points=int(p["dense_min_points"]),
    )
    line_candidates = _collinear_cluster_mask(
        xy,
        h,
        w,
        iters=int(p["line_ransac_iters"]),
        min_inliers=int(p["line_min_inliers"]),
        max_dist_px=float(p["line_max_dist_px"]),
        min_span_frac=float(p["line_min_span_frac"]),
    )
    evidence = _points_on_evidence_mask(xy, evidence_mask, (h, w))

    # 密度或共线只是候选特征，必须与图像结构证据重合才允许剔除。
    # Density/collinearity is only a candidate feature; image evidence must corroborate it.
    dense_reject = dense_candidates & evidence
    line_reject = line_candidates & evidence
    reject = dense_reject | line_reject

    requested_rejected = int(reject.sum())
    max_fraction = max(0.0, min(0.8, float(max_rejected_fraction)))
    max_rejected = min(max(0, n0 - 4), int(math.floor(n0 * max_fraction)))
    limited = requested_rejected > max_rejected
    if limited:
        reject_idx = np.flatnonzero(reject)
        reject[:] = False
        # 输入按亮度降序；优先清除最先挤占名额的结构候选。
        # Input is brightness-sorted; remove early clutter that displaces clean stars first.
        reject[reject_idx[:max_rejected]] = True

    dense_final = dense_reject & reject
    line_final = line_reject & reject
    r_dense = int(dense_final.sum())
    r_line = int((line_final & ~dense_final).sum())
    if r_dense > 0:
        flags.append(_FLAG_DENSE)
        hints.append(
            "局部区域星点过密已剔除（可能为树梢或亮斑）/ "
            "Rejected dense local region (trees or bright clutter)"
        )

    if r_line > 0:
        flags.append(_FLAG_LINE)
        hints.append(
            "共线星点已剔除（可能为电线）/ "
            "Rejected collinear detections (power lines)"
        )

    if limited:
        flags.append(_FLAG_LIMITED)
        hints.append(
            "结构过滤已达到保守上限，保留其余候选 / "
            "Structural filtering reached its conservative cap; remaining candidates kept"
        )

    xy_out = xy[~reject]
    n1 = int(xy_out.shape[0])
    rejected_pts = xy[reject]
    quality: dict[str, Any] = {
        "level": lv,
        "flags": flags,
        "hints": hints,
        "metrics": {
            "input_count": n0,
            "output_count": n1,
            "removed_dense": r_dense,
            "removed_line": r_line,
            "dense_candidates": int(dense_candidates.sum()),
            "line_candidates": int(line_candidates.sum()),
            "evidence_candidates": int(evidence.sum()),
            "requested_rejected": requested_rejected,
            "filter_limited": limited,
        },
        "rejected_centroids_yx": rejected_pts.tolist(),
    }
    return xy_out, quality


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
            "dense_candidates": 0,
            "line_candidates": 0,
            "evidence_candidates": 0,
            "requested_rejected": 0,
            "filter_limited": False,
        },
        "rejected_centroids_yx": [],
    }
