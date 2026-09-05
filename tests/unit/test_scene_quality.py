"""天空结构污染分析测试 / Tests for structural sky-scene contamination analysis."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from ogscope.algorithms.plate_solve.scene_quality import (
    analyze_structural_contamination,
)


def _rich_star_field(seed: int = 7) -> np.ndarray:
    """生成高密度点状星场 / Build a dense point-like star field."""
    rng = np.random.default_rng(seed)
    image = np.full((360, 640, 3), 8, dtype=np.uint8)
    for y, x, value in zip(
        rng.integers(8, 352, 500),
        rng.integers(8, 632, 500),
        rng.integers(120, 256, 500),
        strict=True,
    ):
        cv2.circle(image, (int(x), int(y)), 1, (int(value),) * 3, -1)
    return image


@pytest.mark.unit
def test_rich_star_field_is_not_structural_obstruction() -> None:
    """星点再密也不能独立触发遮挡 / Rich stars alone must not trigger obstruction."""
    result = analyze_structural_contamination(_rich_star_field())
    assert result.has_structural_evidence is False
    assert result.flags == []
    assert not np.any(result.evidence_mask)


@pytest.mark.unit
def test_branch_like_edges_are_detected() -> None:
    """跨画面的树枝结构应提供证据 / Long branch-like edges provide evidence."""
    image = _rich_star_field()
    cv2.line(image, (0, 300), (500, 80), (150, 150, 150), 8)
    cv2.line(image, (180, 220), (100, 50), (130, 130, 130), 5)
    result = analyze_structural_contamination(image)
    assert result.has_structural_evidence is True
    assert "LONG_STRUCTURAL_EDGES" in result.flags
    assert result.metrics["max_line_length_px"] > 70
    assert 1 <= len(result.regions) <= 12
    assert any(region["kind"] == "long_structural_edge" for region in result.regions)
    assert all(len(region["points"]) <= 32 for region in result.regions)


@pytest.mark.unit
def test_large_bright_source_is_detected_but_isolated_stars_are_not() -> None:
    """月面级亮区应被识别，孤立亮星不应 / Detect moon-scale areas, not isolated stars."""
    image = _rich_star_field()
    cv2.circle(image, (450, 100), 35, (255, 255, 255), -1)
    result = analyze_structural_contamination(image)
    assert "LARGE_BRIGHT_REGION" in result.flags
    assert result.metrics["bright_fraction"] > 0.01
    assert any(region["geometry"] == "polygon" for region in result.regions)
