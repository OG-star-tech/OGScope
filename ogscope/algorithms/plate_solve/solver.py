"""
简化星图解算器 / Simplified plate solver
"""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, radians
from typing import Any

import numpy as np

from ogscope.algorithms.star_extract import StarPoint
from ogscope.data.catalog.service import catalog_service


@dataclass(slots=True)
class SolveResult:
    """解算结果 / Solving result"""

    ra_deg: float
    dec_deg: float
    confidence: float
    solve_source: str
    matched_catalog_stars: int
    detected_stars: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "ra_deg": self.ra_deg,
            "dec_deg": self.dec_deg,
            "confidence": self.confidence,
            "solve_source": self.solve_source,
            "matched_catalog_stars": self.matched_catalog_stars,
            "detected_stars": self.detected_stars,
        }


class PlateSolver:
    """基于提示位姿与星表密度的轻量解算 / Lightweight solver with hint and catalog density"""

    def __init__(self, fov_deg: float = 16.0) -> None:
        self.fov_deg = fov_deg

    def solve(
        self,
        stars: list[StarPoint],
        frame_shape: tuple[int, ...],
        hint_ra_deg: float,
        hint_dec_deg: float,
        solve_source: str = "full",
    ) -> SolveResult:
        """解算画面中心坐标 / Solve frame center coordinate"""
        if not stars:
            return SolveResult(
                ra_deg=hint_ra_deg % 360.0,
                dec_deg=float(np.clip(hint_dec_deg, -90.0, 90.0)),
                confidence=0.0,
                solve_source=solve_source,
                matched_catalog_stars=0,
                detected_stars=0,
            )

        height, width = frame_shape[:2]
        points = np.array([[s.x, s.y, s.flux] for s in stars], dtype=np.float64)
        flux = np.clip(points[:, 2], 1e-6, None)
        centroid_x = float(np.average(points[:, 0], weights=flux))
        centroid_y = float(np.average(points[:, 1], weights=flux))
        dx = centroid_x - (width / 2.0)
        dy = centroid_y - (height / 2.0)

        deg_per_pixel = self.fov_deg / max(width, 1)
        dec = float(np.clip(hint_dec_deg - (dy * deg_per_pixel), -90.0, 90.0))
        cos_dec = max(0.01, cos(radians(dec)))
        ra = (hint_ra_deg + (dx * deg_per_pixel / cos_dec)) % 360.0

        nearby_catalog = catalog_service.load_records_for_region(ra_deg=ra, search_bins=1)
        expected_stars = max(1, len(nearby_catalog))
        detected_stars = len(stars)
        matched = min(detected_stars, expected_stars)
        confidence = min(1.0, detected_stars / expected_stars)

        return SolveResult(
            ra_deg=ra,
            dec_deg=dec,
            confidence=float(confidence),
            solve_source=solve_source,
            matched_catalog_stars=matched,
            detected_stars=detected_stars,
        )
