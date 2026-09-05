"""
保守的天空画面结构污染分析 / Conservative structural contamination analysis.

该模块只寻找大亮区和长结构边缘，不使用星点数量判断遮挡，避免把优质密集星场
误认为楼宇、树木或月亮。分析默认仅用于常规解算失败后的回退路径。
This module detects large bright regions and long structural edges only. Star density is
never obstruction evidence, which protects rich star fields from false classification.
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


def analyze_structural_contamination(
    frame_bgr: np.ndarray,
    *,
    downsample_max_side: int = 320,
) -> SceneQualityAnalysis:
    """检测大亮区与长结构边缘 / Detect large bright regions and long structural edges.

    算法刻意保持保守：密集星点和全局纹理不构成证据。大亮区需形成足够大的连通域，
    结构边缘需形成足够长的线段；两者都在缩小图上计算以限制树莓派开销。
    The detector is deliberately conservative: dense stars and global texture are not
    evidence. Bright regions must be large components and edges must form long segments.
    """
    if frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3:
        raise ValueError("frame_bgr must be an HxWx3 BGR image")

    h, w = int(frame_bgr.shape[0]), int(frame_bgr.shape[1])
    if h < 2 or w < 2:
        empty = np.zeros((h, w), dtype=bool)
        return SceneQualityAnalysis(
            evidence_mask=empty,
            flags=[],
            regions=[],
            metrics={
                "analysis_width": w,
                "analysis_height": h,
                "bright_fraction": 0.0,
                "linear_fraction": 0.0,
                "evidence_fraction": 0.0,
                "long_line_count": 0,
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

    evidence_small = np.maximum(bright_mask, line_mask)
    evidence_mask = cv2.resize(
        evidence_small,
        (w, h),
        interpolation=cv2.INTER_NEAREST,
    ).astype(bool)

    bright_fraction = float(np.mean(bright_mask > 0))
    evidence_fraction = float(np.mean(evidence_small > 0))
    flags: list[str] = []
    if bright_fraction >= 0.0005:
        flags.append("LARGE_BRIGHT_REGION")
    if strong_linear_evidence:
        flags.append("LONG_STRUCTURAL_EDGES")

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

    return SceneQualityAnalysis(
        evidence_mask=evidence_mask,
        flags=flags,
        regions=regions,
        metrics={
            "analysis_width": sw,
            "analysis_height": sh,
            "bright_fraction": round(bright_fraction, 6),
            "linear_fraction": round(linear_fraction, 6),
            "evidence_fraction": round(evidence_fraction, 6),
            "long_line_count": long_line_count,
            "max_line_length_px": round(max_line_length, 3),
        },
    )
