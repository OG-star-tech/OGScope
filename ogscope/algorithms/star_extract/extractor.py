"""
星点提取器 / Star extractor
"""

from __future__ import annotations

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

    def __init__(self, max_stars: int = 80) -> None:
        self.max_stars = max_stars

    def extract(self, frame: np.ndarray) -> list[StarPoint]:
        """提取星点 / Extract star points"""
        if frame.ndim == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame.copy()

        # 使用高斯模糊降低高频噪声 / Apply gaussian blur for high-frequency noise
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        _, binary = cv2.threshold(
            blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        contours, _ = cv2.findContours(
            binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        points: list[StarPoint] = []
        for contour in contours:
            area = float(cv2.contourArea(contour))
            if area <= 0.5:
                continue
            m = cv2.moments(contour)
            if m["m00"] <= 0:
                continue
            cx = float(m["m10"] / m["m00"])
            cy = float(m["m01"] / m["m00"])
            mask = np.zeros_like(gray, dtype=np.uint8)
            cv2.drawContours(mask, [contour], -1, color=255, thickness=-1)
            flux = float(cv2.mean(gray, mask=mask)[0] * area)
            points.append(StarPoint(x=cx, y=cy, flux=flux, area=area))

        points.sort(key=lambda p: p.flux, reverse=True)
        return points[: self.max_stars]
