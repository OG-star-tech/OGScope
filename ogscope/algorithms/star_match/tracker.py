"""
快速跟踪器 / Fast tracker
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from ogscope.algorithms.star_extract import StarPoint


@dataclass(slots=True)
class TrackResult:
    """跟踪结果 / Tracking result"""

    delta_x: float
    delta_y: float
    matched_points: int
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "delta_x": self.delta_x,
            "delta_y": self.delta_y,
            "matched_points": self.matched_points,
            "confidence": self.confidence,
        }


class FastTracker:
    """基于质心偏移的轻量跟踪 / Lightweight tracking based on centroid shift"""

    def track(
        self, previous: list[StarPoint], current: list[StarPoint]
    ) -> TrackResult:
        """估计帧间位移 / Estimate inter-frame shift"""
        if not previous or not current:
            return TrackResult(delta_x=0.0, delta_y=0.0, matched_points=0, confidence=0.0)

        prev = np.array([[p.x, p.y, max(p.flux, 1e-6)] for p in previous], dtype=np.float64)
        cur = np.array([[p.x, p.y, max(p.flux, 1e-6)] for p in current], dtype=np.float64)
        prev_cx = float(np.average(prev[:, 0], weights=prev[:, 2]))
        prev_cy = float(np.average(prev[:, 1], weights=prev[:, 2]))
        cur_cx = float(np.average(cur[:, 0], weights=cur[:, 2]))
        cur_cy = float(np.average(cur[:, 1], weights=cur[:, 2]))

        matched_points = min(len(previous), len(current))
        confidence = min(1.0, matched_points / 20.0)
        return TrackResult(
            delta_x=cur_cx - prev_cx,
            delta_y=cur_cy - prev_cy,
            matched_points=matched_points,
            confidence=confidence,
        )
