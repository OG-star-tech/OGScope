"""遮挡感知解算回退测试 / Tests for obstruction-aware solve fallback."""

from __future__ import annotations

import sys
import types
from typing import Any

import cv2
import numpy as np
import pytest

from ogscope.algorithms.plate_solve.solver import PlateSolver


class _FakeTetra:
    """按顺序返回预设状态 / Return configured solve statuses in order."""

    def __init__(self, statuses: list[int]) -> None:
        self.statuses = statuses
        self.calls: list[np.ndarray] = []

    def solve_from_centroids(
        self,
        centroids: np.ndarray,
        _shape: tuple[int, int],
        **_kwargs: Any,
    ) -> dict[str, Any]:
        self.calls.append(np.asarray(centroids).copy())
        status = self.statuses[len(self.calls) - 1]
        if status == 1:
            return {
                "status": 1,
                "RA": 12.0,
                "Dec": 80.0,
                "Roll": 0.0,
                "FOV": 16.0,
                "Matches": 8,
                "Prob": 0.001,
                "RMSE": 7.5,
                "T_solve": 4.0,
            }
        return {"status": status, "T_solve": 4.0}


def _patch_extractor(monkeypatch: pytest.MonkeyPatch, centroids: np.ndarray) -> None:
    """替换 Tetra3 提星函数 / Replace the Tetra3 centroid extractor."""

    def _extractor(*_args: Any, **_kwargs: Any) -> np.ndarray:
        return centroids.copy()

    fake_module = types.ModuleType("tetra3")
    fake_module.get_centroids_from_image = _extractor  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tetra3", fake_module)


@pytest.mark.unit
def test_normal_success_skips_scene_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    """常规成功不能被遮挡分类推翻 / Normal success must bypass obstruction analysis."""
    centroids = np.asarray([[20.0 + i * 8, 30.0 + i * 11] for i in range(12)])
    _patch_extractor(monkeypatch, centroids)
    fake = _FakeTetra([1])
    solver = PlateSolver()
    monkeypatch.setattr(solver, "_tetra", lambda: fake)

    def _unexpected(_image: np.ndarray) -> None:
        raise AssertionError("scene analysis must not run after a normal match")

    monkeypatch.setattr(
        "ogscope.algorithms.plate_solve.solver.analyze_structural_contamination",
        _unexpected,
    )
    result = solver.solve_from_bgr_frame(
        np.zeros((360, 640, 3), dtype=np.uint8),
        max_stars=8,
    )
    assert result.status == "MATCH_FOUND"
    assert len(fake.calls) == 1
    assert result.centroid_quality is not None
    assert result.centroid_quality["scene"]["analyzed"] is False


@pytest.mark.unit
def test_failed_normal_solve_retries_after_structural_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """失败且有树枝证据时使用过滤候选重试 / Retry filtered candidates after branch evidence."""
    image = np.full((360, 640, 3), 8, dtype=np.uint8)
    cv2.line(image, (0, 300), (500, 80), (160, 160, 160), 8)
    line_points = [[300.0 - i * 13.75, i * 31.25] for i in range(16)]
    clean_points = [[30.0 + (i % 4) * 70, 350.0 + (i // 4) * 45] for i in range(16)]
    centroids = np.asarray(line_points + clean_points, dtype=np.float64)
    _patch_extractor(monkeypatch, centroids)
    fake = _FakeTetra([2, 1])
    solver = PlateSolver()
    monkeypatch.setattr(solver, "_tetra", lambda: fake)

    result = solver.solve_from_bgr_frame(image, max_stars=16)
    assert result.status == "MATCH_FOUND"
    assert len(fake.calls) == 2
    assert not np.array_equal(fake.calls[0], fake.calls[1])
    assert result.centroid_quality is not None
    assert result.centroid_quality["fallback_attempted"] is True
    assert result.centroid_quality["normal_status"] == "NO_MATCH"
    assert result.centroid_quality["fallback_status"] == "MATCH_FOUND"
    assert result.centroid_quality["metrics"]["requested_rejected"] > 0
    assert result.solve_overlay is not None
    regions = result.solve_overlay["scene_evidence_regions"]
    assert 1 <= len(regions) <= 12
    assert all(
        0.0 <= point["x"] <= image.shape[1] and 0.0 <= point["y"] <= image.shape[0]
        for region in regions
        for point in region["points"]
    )


@pytest.mark.unit
def test_failed_solve_in_rich_field_does_not_filter_by_density(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """密集星场失败也不能凭密度进入过滤回退 / Failure in rich fields does not justify filtering."""
    rng = np.random.default_rng(11)
    image = np.full((360, 640, 3), 8, dtype=np.uint8)
    points: list[list[float]] = []
    for y, x, value in zip(
        rng.integers(8, 352, 300),
        rng.integers(8, 632, 300),
        rng.integers(120, 230, 300),
        strict=True,
    ):
        cv2.circle(image, (int(x), int(y)), 1, (int(value),) * 3, -1)
        points.append([float(y), float(x)])
    _patch_extractor(monkeypatch, np.asarray(points))
    fake = _FakeTetra([2])
    solver = PlateSolver()
    monkeypatch.setattr(solver, "_tetra", lambda: fake)

    result = solver.solve_from_bgr_frame(image, max_stars=80)
    assert result.status == "NO_MATCH"
    assert len(fake.calls) == 1
    assert result.centroid_quality is not None
    assert result.centroid_quality["fallback_attempted"] is False
    assert result.centroid_quality["scene"]["has_structural_evidence"] is False
