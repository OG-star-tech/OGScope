"""ESA tetra3 输出的状态推断测试 / Tests for inferring status from ESA tetra3 output.

设备镜像安装的是 ESA 上游 tetra3，它的结果没有 status 字段。
The device image ships upstream ESA tetra3, whose results carry no status field.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import numpy as np
import pytest

from ogscope.algorithms.plate_solve.solver import PlateSolver
from ogscope.algorithms.star_extract import StarPoint

_TIMEOUT_MS = 8000.0


def _esa_solution() -> dict[str, Any]:
    """ESA tetra3 的成功结果（无 status）/ An ESA tetra3 solution (no status)."""
    return {
        "RA": 309.22,
        "Dec": 57.74,
        "Roll": 265.57,
        "FOV": 13.01,
        "distortion": 0.0,
        "RMSE": 16.6,
        "Matches": 20,
        "Prob": 1.5e-32,
        "epoch_equinox": 2000,
        "epoch_proper_motion": 2026.0,
        "T_solve": 210.5,
    }


def _esa_failure(t_solve_ms: float) -> dict[str, Any]:
    """ESA tetra3 的失败结果，形状与上游一致 / An ESA tetra3 failure, as upstream returns it."""
    return {
        "RA": None,
        "Dec": None,
        "Roll": None,
        "FOV": None,
        "distortion": None,
        "RMSE": None,
        "Matches": None,
        "Prob": None,
        "epoch_equinox": None,
        "epoch_proper_motion": None,
        "T_solve": t_solve_ms,
    }


class _FakeEsaTetra:
    """按顺序返回预设的 ESA 结果 / Return configured ESA results in order."""

    def __init__(self, outputs: list[dict[str, Any]]) -> None:
        self.outputs = outputs
        self.calls = 0

    def solve_from_centroids(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        return dict(self.outputs[self.calls - 1])


def _solver_with(
    monkeypatch: pytest.MonkeyPatch, outputs: list[dict[str, Any]]
) -> tuple[PlateSolver, _FakeEsaTetra]:
    centroids = np.asarray([[20.0 + i * 8, 30.0 + i * 11] for i in range(12)])
    fake_module = types.ModuleType("tetra3")
    fake_module.get_centroids_from_image = (  # type: ignore[attr-defined]
        lambda *_a, **_k: centroids.copy()
    )
    monkeypatch.setitem(sys.modules, "tetra3", fake_module)
    fake = _FakeEsaTetra(outputs)
    solver = PlateSolver(solve_timeout_ms=int(_TIMEOUT_MS))
    monkeypatch.setattr(solver, "_tetra", lambda: fake)
    return solver, fake


def _solve_frame(solver: PlateSolver) -> Any:
    return solver.solve_from_bgr_frame(
        np.zeros((360, 640, 3), dtype=np.uint8),
        max_stars=8,
    )


@pytest.mark.unit
def test_esa_solution_is_match_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """有 RA/Dec 的 ESA 结果即为匹配 / An ESA result with RA/Dec is a match."""
    solver, _fake = _solver_with(monkeypatch, [_esa_solution()])

    result = _solve_frame(solver)

    assert result.status == "MATCH_FOUND"
    assert result.status_code == 1
    assert result.to_dict()["status"] == "MATCH_FOUND"
    assert result.ra_deg == pytest.approx(309.22)
    assert result.matches == 20


@pytest.mark.unit
def test_esa_solution_skips_the_obstruction_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ESA 匹配不能再触发场景分析与二次解算 / An ESA match must not trigger scene analysis."""
    solver, fake = _solver_with(monkeypatch, [_esa_solution()])

    def _unexpected(_image: np.ndarray) -> None:
        raise AssertionError("scene analysis must not run after a match")

    monkeypatch.setattr(
        "ogscope.algorithms.plate_solve.solver.analyze_structural_contamination",
        _unexpected,
    )

    result = _solve_frame(solver)

    assert result.status == "MATCH_FOUND"
    assert fake.calls == 1


@pytest.mark.unit
def test_esa_exhausted_search_is_no_match(monkeypatch: pytest.MonkeyPatch) -> None:
    """超时前放弃即为无匹配 / Giving up before the timeout is a no match."""
    solver, _fake = _solver_with(monkeypatch, [_esa_failure(900.0)])

    result = _solve_frame(solver)

    assert result.status == "NO_MATCH"
    assert result.status_code == 2


@pytest.mark.unit
def test_esa_failure_past_the_timeout_is_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """耗时达到超时的失败即为超时 / A failure that used up the timeout is a timeout."""
    solver, _fake = _solver_with(monkeypatch, [_esa_failure(_TIMEOUT_MS + 12.0)])

    result = _solve_frame(solver)

    assert result.status == "TIMEOUT"
    assert result.status_code == 3


@pytest.mark.unit
def test_star_list_solve_maps_esa_solution(monkeypatch: pytest.MonkeyPatch) -> None:
    """星点列表路径同样推断状态 / The star-list path infers the status too."""
    solver, _fake = _solver_with(monkeypatch, [_esa_solution()])
    stars = [
        StarPoint(x=30.0 + i * 11, y=20.0 + i * 8, flux=100.0 - i, area=9.0)
        for i in range(12)
    ]

    result = solver.solve(stars, (360, 640))

    assert result.status == "MATCH_FOUND"
    assert result.status_code == 1


@pytest.mark.unit
def test_cedar_status_is_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    """已有 status 的 cedar-solve 结果保持不变 / A cedar-solve status is left as is."""
    solver, _fake = _solver_with(
        monkeypatch, [{**_esa_failure(_TIMEOUT_MS + 12.0), "status": 2}]
    )

    result = _solve_frame(solver)

    assert result.status == "NO_MATCH"
