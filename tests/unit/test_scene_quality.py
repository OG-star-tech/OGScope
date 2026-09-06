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
def test_smooth_sky_gradient_is_not_dark_structure() -> None:
    """平滑天光渐变不能被当作暗树 / A smooth sky gradient is not a dark tree."""
    gradient = np.linspace(28, 92, 640, dtype=np.uint8)
    gray = np.repeat(gradient[np.newaxis, :], 360, axis=0)
    image = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    result = analyze_structural_contamination(image)

    assert "DARK_EXTENDED_STRUCTURE" not in result.flags
    assert result.metrics["dark_component_count"] == 0
    assert result.metrics["dark_fraction"] == 0.0


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


@pytest.mark.unit
def test_mixed_bright_and_dark_trees_include_low_contrast_structure() -> None:
    """亮暗树同框时保留低对比暗结构 / Retain low-contrast dark structure beside bright trees."""
    image = np.full((360, 640, 3), 100, dtype=np.uint8)
    rng = np.random.default_rng(12)
    for y, x, value in zip(
        rng.integers(8, 352, 220),
        rng.integers(8, 632, 220),
        rng.integers(135, 256, 220),
        strict=True,
    ):
        cv2.circle(image, (int(x), int(y)), 1, (int(value),) * 3, -1)

    cv2.line(image, (0, 345), (230, 70), (225, 225, 225), 9)
    dark = (78, 78, 78)
    paths = [
        [(639, 350), (585, 300), (560, 245), (515, 205), (500, 150)],
        [(590, 305), (615, 245), (600, 205), (630, 160)],
        [(550, 250), (525, 220), (535, 175), (510, 140)],
    ]
    for points in paths:
        cv2.polylines(
            image,
            [np.asarray(points, dtype=np.int32)],
            False,
            dark,
            4,
            lineType=cv2.LINE_AA,
        )
    for center, radius in [((560, 180), 25), ((600, 195), 22), ((515, 155), 24)]:
        cv2.circle(image, center, radius, dark, -1, lineType=cv2.LINE_AA)

    result = analyze_structural_contamination(image)

    assert "DARK_EXTENDED_STRUCTURE" in result.flags
    assert result.metrics["dark_component_count"] >= 1
    assert result.metrics["dark_fraction"] > 0.01
    assert any(region["kind"] == "dark_structural_region" for region in result.regions)
    assert result.evidence_region_labels.shape == (
        result.metrics["analysis_height"],
        result.metrics["analysis_width"],
    )
    dark_roi = result.evidence_mask[80:360, 400:640]
    assert float(np.mean(dark_roi)) > 0.02
