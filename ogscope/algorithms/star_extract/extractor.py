"""
星点提取器 / Star extractor
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np


@dataclass(slots=True)
class StarPoint:
    """星点数据 / Star point data"""

    x: float
    y: float
    flux: float
    area: float

    def to_dict(self) -> dict[str, Any]:
        return {"x": self.x, "y": self.y, "flux": self.flux, "area": self.area}


class StarExtractor:
    """简单星点提取 / Lightweight star extraction"""

    # 大图先缩小再提星，降低内存与轮廓数量 / Downscale before extract (RAM + contour count on SBCs)
    _max_input_side: int = 1920
    # 椒盐噪声多时 OTSU 轮廓可上万，逐轮廓整幅 mask 会 OOM；过多则缩小重试 / Too many contours → downscale & retry
    _max_contours_before_downscale: int = 6000
    _min_side_for_downscale: int = 400
    # 几何过滤：与噪点体积区分，减轻 Tetra3 假星导致的 TIMEOUT / Reject noise blobs vs point-like stars
    _min_star_area: float = 2.0
    _max_star_area_frac: float = (
        0.0035  # 单连通域面积不超过画幅比例 / Max contour area vs frame
    )
    _min_circularity: float = 0.12  # 4πA/P²；细长热噪、条纹偏低 / Elongated junk is low

    def __init__(self, max_stars: int = 80) -> None:
        self.max_stars = max_stars

    def extract(self, frame: np.ndarray) -> list[StarPoint]:
        """提取星点 / Extract star points"""
        if frame.ndim == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame.copy()

        h, w = gray.shape[:2]
        side = max(h, w)
        if side > self._max_input_side:
            scale0 = self._max_input_side / float(side)
            gray = cv2.resize(
                gray,
                (max(1, int(w * scale0)), max(1, int(h * scale0))),
                interpolation=cv2.INTER_AREA,
            )
        return self._extract_gray_scaled(gray, scale=1.0)

    def _extract_gray_scaled(self, gray: np.ndarray, scale: float) -> list[StarPoint]:
        """在灰度图上提星；scale 为相对原图的坐标倍率 / Extract on gray; scale maps coords to original frame."""
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        _, binary = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        # 去掉孤立椒盐点，减少伪轮廓 / Morph open removes salt noise, fewer false contours
        _k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, _k)

        contours, _ = cv2.findContours(
            binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        h, w = gray.shape[:2]
        if (
            len(contours) > self._max_contours_before_downscale
            and min(h, w) > self._min_side_for_downscale
        ):
            small = cv2.resize(
                gray,
                (max(1, w // 2), max(1, h // 2)),
                interpolation=cv2.INTER_AREA,
            )
            return self._extract_gray_scaled(small, scale * 2.0)

        # 已缩到最小仍极多轮廓时只保留面积最大的一批，避免 OOM / Cap contour count if still huge
        if len(contours) > self._max_contours_before_downscale:
            contours = heapq.nlargest(
                self._max_contours_before_downscale,
                contours,
                key=cv2.contourArea,
            )

        frame_px = float(h * w)
        max_area = self._max_star_area_frac * frame_px

        points: list[StarPoint] = []
        for contour in contours:
            area = float(cv2.contourArea(contour))
            if area < self._min_star_area:
                continue
            if area > max_area:
                continue
            peri = float(cv2.arcLength(contour, True))
            if peri > 0.0:
                circ = (4.0 * math.pi * area) / (peri * peri)
                if circ < self._min_circularity:
                    continue
            m = cv2.moments(contour)
            if m["m00"] <= 0:
                continue
            cx = float(m["m10"] / m["m00"]) * scale
            cy = float(m["m01"] / m["m00"]) * scale
            mask = np.zeros_like(gray, dtype=np.uint8)
            cv2.drawContours(mask, [contour], -1, color=255, thickness=-1)
            flux = float(cv2.mean(gray, mask=mask)[0] * area)
            points.append(StarPoint(x=cx, y=cy, flux=flux, area=area))

        points.sort(key=lambda p: p.flux, reverse=True)
        return points[: self.max_stars]
