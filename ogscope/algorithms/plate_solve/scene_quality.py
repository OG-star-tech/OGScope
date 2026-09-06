"""
保守的天空画面结构污染分析 / Conservative structural contamination analysis.

该模块寻找大亮区、长结构边缘和低对比暗结构，不使用星点数量判断遮挡，避免把
优质密集星场误认为楼宇、树木或月亮。分析默认仅用于常规解算失败后的回退路径。
This module detects large bright regions, long structural edges, and low-contrast dark
structures. Star density is never obstruction evidence, protecting rich star fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np


@dataclass(slots=True)
class SceneQualityAnalysis:
    """结构证据掩膜及可序列化指标 / Structural evidence mask and JSON-safe metrics."""

    evidence_mask: np.ndarray
    evidence_region_labels: np.ndarray
    flags: list[str]
    metrics: dict[str, Any]
    regions: list[dict[str, Any]]

    @property
    def has_structural_evidence(self) -> bool:
        """是否存在足够结构证据 / Whether meaningful structural evidence exists."""
        return bool(self.flags)

    def to_dict(self) -> dict[str, Any]:
        """仅导出诊断数据，不导出像素掩膜 / Export diagnostics without the pixel mask."""
        return {
            "has_structural_evidence": self.has_structural_evidence,
            "flags": list(self.flags),
            "metrics": dict(self.metrics),
            "regions": list(self.regions),
        }


def _odd_kernel_size(value: float, *, minimum: int, maximum: int) -> int:
    """限制形态学核为有界奇数 / Clamp a morphology kernel to a bounded odd size."""
    size = max(minimum, min(maximum, int(round(value))))
    if size % 2 == 0:
        size += 1 if size < maximum else -1
    return size


def _polygon_regions_from_mask(
    mask: np.ndarray,
    *,
    kind: str,
    limit: int = 6,
) -> list[dict[str, Any]]:
    """从结构掩膜导出有界轮廓 / Export bounded polygons from a structure mask."""
    contours, _ = cv2.findContours(
        (mask > 0).astype(np.uint8),
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    regions: list[dict[str, Any]] = []
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:limit]:
        perimeter = float(cv2.arcLength(contour, True))
        approximated = cv2.approxPolyDP(
            contour,
            max(1.0, perimeter * 0.018),
            True,
        ).reshape(-1, 2)
        if approximated.shape[0] > 32:
            step = int(np.ceil(approximated.shape[0] / 32.0))
            approximated = approximated[::step]
        if approximated.shape[0] < 3:
            x, y, box_w, box_h = cv2.boundingRect(contour)
            approximated = np.asarray(
                [
                    [x, y],
                    [x + box_w, y],
                    [x + box_w, y + box_h],
                    [x, y + box_h],
                ],
                dtype=np.int32,
            )
        regions.append(
            {
                "kind": kind,
                "geometry": "polygon",
                "points": [
                    [float(point[0]), float(point[1])] for point in approximated
                ],
            }
        )
    return regions


def _detect_dark_extended_structures(
    gray: np.ndarray,
) -> tuple[np.ndarray, list[dict[str, Any]], dict[str, Any]]:
    """检测相对局部背景更暗的延展结构 / Detect extended structures darker than local background.

    两个黑帽尺度覆盖细枝与较粗树冠边缘。先用小型中值滤波抑制点状星像，
    再要求连通域具有足够面积和跨度，因此密集星点不会单独形成暗结构证据。
    Two black-hat scales cover thin branches and broader canopy edges. A small
    median filter suppresses point-like stars before components must pass both
    area and span gates, so star density alone is not dark-structure evidence.
    """
    sh, sw = int(gray.shape[0]), int(gray.shape[1])
    if sh < 8 or sw < 8:
        return (
            np.zeros((sh, sw), dtype=np.uint8),
            [],
            {
                "dark_component_count": 0,
                "dark_thresholds": [],
                "dark_kernel_sizes": [],
            },
        )

    min_side = min(sh, sw)
    kernel_sizes = (
        _odd_kernel_size(min_side * 0.05, minimum=7, maximum=13),
        _odd_kernel_size(min_side * 0.12, minimum=15, maximum=25),
    )
    point_suppressed = cv2.medianBlur(gray, 3)
    combined = np.zeros((sh, sw), dtype=np.uint8)
    thresholds: list[float] = []

    for kernel_size in kernel_sizes:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (kernel_size, kernel_size),
        )
        closed = cv2.morphologyEx(point_suppressed, cv2.MORPH_CLOSE, kernel)
        residual = cv2.subtract(closed, point_suppressed)
        median = float(np.median(residual))
        mad = float(np.median(np.abs(residual.astype(np.float32) - median)))
        threshold = max(5.0, median + 4.0 * 1.4826 * mad)
        thresholds.append(round(threshold, 3))
        seed = (residual >= threshold).astype(np.uint8)
        seed = cv2.morphologyEx(
            seed,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
        )
        combined = np.maximum(combined, seed)

    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(
        combined,
        connectivity=8,
    )
    retained = np.zeros((sh, sw), dtype=np.uint8)
    min_area = max(8, int(round(sh * sw * 0.00015)))
    min_span = max(12, int(round(min_side * 0.10)))
    retained_count = 0
    for label in range(1, component_count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        box_w = int(stats[label, cv2.CC_STAT_WIDTH])
        box_h = int(stats[label, cv2.CC_STAT_HEIGHT])
        if area < min_area or max(box_w, box_h) < min_span:
            continue
        retained[labels == label] = 1
        retained_count += 1

    if retained_count:
        dilation_size = _odd_kernel_size(
            min_side * 0.035,
            minimum=5,
            maximum=9,
        )
        retained = cv2.dilate(
            retained,
            cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE,
                (dilation_size, dilation_size),
            ),
            iterations=1,
        )

    regions = _polygon_regions_from_mask(
        retained,
        kind="dark_structural_region",
    )
    return (
        retained,
        regions,
        {
            "dark_component_count": retained_count,
            "dark_thresholds": thresholds,
            "dark_kernel_sizes": list(kernel_sizes),
        },
    )


def analyze_structural_contamination(
    frame_bgr: np.ndarray,
    *,
    downsample_max_side: int = 320,
) -> SceneQualityAnalysis:
    """检测大亮区与长结构边缘 / Detect large bright regions and long structural edges.

    算法刻意保持保守：密集星点和全局纹理不构成证据。亮区、长边缘和暗结构均需
    通过面积或跨度门槛；所有通道都在缩小图上计算以限制树莓派开销。
    The detector is deliberately conservative: dense stars and global texture are not
    evidence. Bright, linear, and dark structures must pass area or span gates.
    """
    if frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3:
        raise ValueError("frame_bgr must be an HxWx3 BGR image")

    h, w = int(frame_bgr.shape[0]), int(frame_bgr.shape[1])
    if h < 2 or w < 2:
        empty = np.zeros((h, w), dtype=bool)
        return SceneQualityAnalysis(
            evidence_mask=empty,
            evidence_region_labels=np.zeros((h, w), dtype=np.uint16),
            flags=[],
            regions=[],
            metrics={
                "analysis_width": w,
                "analysis_height": h,
                "bright_fraction": 0.0,
                "linear_fraction": 0.0,
                "dark_fraction": 0.0,
                "evidence_fraction": 0.0,
                "long_line_count": 0,
                "dark_component_count": 0,
            },
        )

    side = max(h, w)
    scale = min(1.0, max(64, int(downsample_max_side)) / float(side))
    sw = max(2, int(round(w * scale)))
    sh = max(2, int(round(h * scale)))
    small = cv2.resize(frame_bgr, (sw, sh), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

    # 月面、路灯和强反光需要形成“大而亮”的连通域；孤立饱和星点不会通过面积门槛。
    # Moon/light/glare must form a large bright component; isolated saturated stars fail it.
    bright_seed = (gray >= 238).astype(np.uint8)
    bright_seed = cv2.morphologyEx(
        bright_seed,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
    )
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(
        bright_seed, connectivity=8
    )
    bright_mask = np.zeros((sh, sw), dtype=np.uint8)
    bright_regions: list[tuple[int, int, int, int, int]] = []
    min_bright_area = max(18, int(round(sh * sw * 0.00045)))
    for label in range(1, component_count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        box_w = int(stats[label, cv2.CC_STAT_WIDTH])
        box_h = int(stats[label, cv2.CC_STAT_HEIGHT])
        if area >= min_bright_area and max(box_w, box_h) >= 6:
            bright_mask[labels == label] = 1
            bright_regions.append(
                (
                    int(stats[label, cv2.CC_STAT_LEFT]),
                    int(stats[label, cv2.CC_STAT_TOP]),
                    box_w,
                    box_h,
                    area,
                )
            )
    if np.any(bright_mask):
        bright_mask = cv2.dilate(
            bright_mask,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)),
            iterations=1,
        )

    # 先模糊掉点状星像，再寻找跨越画面一定尺度的线段（屋檐、树枝、电线等）。
    # Blur point-like stars before finding long edges from roofs, branches, or wires.
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    median = float(np.median(blurred))
    low = int(max(18.0, min(90.0, median * 0.55)))
    high = int(max(low + 20, min(180.0, median * 1.45 + 30.0)))
    edges = cv2.Canny(blurred, low, high)
    min_side = min(sh, sw)
    min_line_length = max(20, int(round(min_side * 0.18)))
    max_line_gap = max(3, int(round(min(sh, sw) * 0.025)))
    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180.0,
        threshold=max(18, int(round(min_line_length * 0.60))),
        minLineLength=min_line_length,
        maxLineGap=max_line_gap,
    )
    line_mask = np.zeros((sh, sw), dtype=np.uint8)
    long_line_count = 0
    max_line_length = 0.0
    line_regions: list[tuple[int, int, int, int, float]] = []
    if lines is not None:
        line_width = max(5, int(round(min_side * 0.035)))
        for raw_line in lines[:, 0, :]:
            x1, y1, x2, y2 = (int(v) for v in raw_line)
            cv2.line(line_mask, (x1, y1), (x2, y2), 1, thickness=line_width)
            long_line_count += 1
            max_line_length = max(
                max_line_length,
                float(np.hypot(x2 - x1, y2 - y1)),
            )
            line_regions.append((x1, y1, x2, y2, float(np.hypot(x2 - x1, y2 - y1))))

    linear_fraction = float(np.mean(line_mask > 0))
    strong_linear_evidence = max_line_length >= min_side * 0.40 or (
        long_line_count >= 2 and linear_fraction >= 0.015
    )
    if not strong_linear_evidence:
        # 随机密集星点偶尔会形成短 Hough 线；不把弱巧合写入证据掩膜。
        # Dense random stars can form short Hough coincidences; discard weak line evidence.
        line_mask[:] = 0
        linear_fraction = 0.0
        line_regions = []

    dark_mask, dark_regions, dark_metrics = _detect_dark_extended_structures(gray)

    evidence_small = np.maximum(np.maximum(bright_mask, line_mask), dark_mask)
    _, evidence_region_labels = cv2.connectedComponents(
        (evidence_small > 0).astype(np.uint8),
        connectivity=8,
    )
    evidence_mask = cv2.resize(
        evidence_small,
        (w, h),
        interpolation=cv2.INTER_NEAREST,
    ).astype(bool)

    bright_fraction = float(np.mean(bright_mask > 0))
    dark_fraction = float(np.mean(dark_mask > 0))
    evidence_fraction = float(np.mean(evidence_small > 0))
    flags: list[str] = []
    if bright_fraction >= 0.0005:
        flags.append("LARGE_BRIGHT_REGION")
    if strong_linear_evidence:
        flags.append("LONG_STRUCTURAL_EDGES")
    if dark_metrics["dark_component_count"]:
        flags.append("DARK_EXTENDED_STRUCTURE")

    # 只导出少量几何证据，不导出位图；坐标仍在分析小图上，解算层统一缩放回原图。
    # Export bounded geometry rather than a bitmap; the solve layer scales it to source pixels.
    regions: list[dict[str, Any]] = []
    for x, y, box_w, box_h, _area in sorted(
        bright_regions, key=lambda item: item[4], reverse=True
    )[:6]:
        regions.append(
            {
                "kind": "large_bright_region",
                "geometry": "polygon",
                "points": [
                    [float(x), float(y)],
                    [float(x + box_w), float(y)],
                    [float(x + box_w), float(y + box_h)],
                    [float(x), float(y + box_h)],
                ],
            }
        )
    for x1, y1, x2, y2, _length in sorted(
        line_regions, key=lambda item: item[4], reverse=True
    )[:6]:
        regions.append(
            {
                "kind": "long_structural_edge",
                "geometry": "polyline",
                "points": [[float(x1), float(y1)], [float(x2), float(y2)]],
            }
        )
    regions.extend(dark_regions[: max(0, 12 - len(regions))])

    return SceneQualityAnalysis(
        evidence_mask=evidence_mask,
        evidence_region_labels=evidence_region_labels.astype(np.uint16),
        flags=flags,
        regions=regions,
        metrics={
            "analysis_width": sw,
            "analysis_height": sh,
            "bright_fraction": round(bright_fraction, 6),
            "linear_fraction": round(linear_fraction, 6),
            "dark_fraction": round(dark_fraction, 6),
            "evidence_fraction": round(evidence_fraction, 6),
            "long_line_count": long_line_count,
            "max_line_length_px": round(max_line_length, 3),
            **dark_metrics,
        },
    )
