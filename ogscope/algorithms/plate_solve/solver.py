"""
基于 Tetra3 (Cedar-Solve) 的星图解算 / Plate solving via Tetra3 (Cedar-Solve)
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from ogscope.algorithms.star_extract import StarPoint
from ogscope.config import Settings, get_settings

_STATUS_NAMES: dict[int, str] = {
    1: "MATCH_FOUND",
    2: "NO_MATCH",
    3: "TIMEOUT",
    4: "CANCELLED",
    5: "TOO_FEW",
}


def _json_safe(obj: Any) -> Any:
    """将 numpy 标量/数组等转为 JSON/FastAPI 可序列化类型 / JSON-serializable conversion for API."""
    if obj is None or isinstance(obj, (str, bool, int, float)):
        return obj
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(x) for x in obj]
    if isinstance(obj, set):
        return [_json_safe(x) for x in obj]
    return obj

_tetra_lock = threading.Lock()
_tetra_instance: Any = None
_tetra_load_key: str | None = None


def _resolve_database_path(settings: Settings) -> Path | str:
    """选择图案库路径：环境配置 > data/plate_solve > 包内默认名 / Resolve pattern DB path."""
    if settings.solver_tetra_database_path is not None:
        return settings.solver_tetra_database_path.expanduser().resolve()
    candidate = settings.plate_solve_dir / "default_database.npz"
    if candidate.is_file():
        return candidate
    return "default_database"


def _get_tetra3(settings: Settings) -> Any:
    """懒加载单例 / Lazy singleton Tetra3."""
    global _tetra_instance, _tetra_load_key
    key = str(_resolve_database_path(settings))
    with _tetra_lock:
        if _tetra_instance is not None and _tetra_load_key == key:
            return _tetra_instance
        from tetra3 import Tetra3  # noqa: PLC0415 — after vendor path

        load_arg: Path | str = _resolve_database_path(settings)
        _tetra_instance = Tetra3(load_arg)
        _tetra_load_key = key
        return _tetra_instance


def reset_tetra3_singleton_for_tests() -> None:
    """测试用：清空单例 / Tests: clear singleton."""
    global _tetra_instance, _tetra_load_key
    with _tetra_lock:
        _tetra_instance = None
        _tetra_load_key = None


@dataclass(slots=True)
class SolveResult:
    """解算结果（Tetra3）/ Tetra3 solving result"""

    ra_deg: float
    dec_deg: float
    detected_stars: int
    solve_source: str
    status: str
    status_code: int | None
    roll_deg: float | None
    fov_deg: float | None
    matches: int | None
    prob: float | None
    rmse_arcsec: float | None
    t_solve_ms: float | None
    t_extract_ms: float | None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        base = {
            "ra_deg": self.ra_deg,
            "dec_deg": self.dec_deg,
            "detected_stars": self.detected_stars,
            "solve_source": self.solve_source,
            "status": self.status,
            "status_code": self.status_code,
            "roll_deg": self.roll_deg,
            "fov_deg": self.fov_deg,
            "matches": self.matches,
            "prob": self.prob,
            "rmse_arcsec": self.rmse_arcsec,
            "t_solve_ms": self.t_solve_ms,
            "t_extract_ms": self.t_extract_ms,
        }
        if self.raw:
            # Tetra3 原始字段含 numpy 标量（如 uint16），FastAPI 无法直接 JSON 编码 / Tetra3 raw may contain numpy scalars
            base["tetra"] = _json_safe(self.raw)
        return base


class PlateSolver:
    """Tetra3 星图解算封装 / Tetra3 plate solver wrapper"""

    def __init__(
        self,
        fov_deg: float = 16.0,
        fov_max_error_deg: float | None = None,
        solve_timeout_ms: int = 8000,
    ) -> None:
        self.fov_deg = fov_deg
        self.fov_max_error_deg = fov_max_error_deg
        self.solve_timeout_ms = solve_timeout_ms

    def _tetra(self) -> Any:
        return _get_tetra3(get_settings())

    def solve(
        self,
        stars: list[StarPoint],
        frame_shape: tuple[int, ...],
        hint_ra_deg: float = 0.0,
        hint_dec_deg: float = 0.0,
        solve_source: str = "full",
        fov_estimate: float | None = None,
        fov_max_error: float | None = None,
        solve_timeout_ms: int | None = None,
    ) -> SolveResult:
        """解算画面中心赤道坐标 / Solve frame center RA/Dec.

        hint_ra_deg / hint_dec_deg 对 Tetra3 无影响，仅保留 API 兼容 / Hints ignored by Tetra3.
        """
        del hint_ra_deg, hint_dec_deg
        height, width = int(frame_shape[0]), int(frame_shape[1])
        fov_est = float(fov_estimate if fov_estimate is not None else self.fov_deg)
        fov_err = fov_max_error if fov_max_error is not None else self.fov_max_error_deg
        timeout = float(
            solve_timeout_ms if solve_timeout_ms is not None else self.solve_timeout_ms
        )

        if len(stars) < 4:
            return SolveResult(
                ra_deg=0.0,
                dec_deg=0.0,
                detected_stars=len(stars),
                solve_source=solve_source,
                status="TOO_FEW",
                status_code=5,
                roll_deg=None,
                fov_deg=None,
                matches=None,
                prob=None,
                rmse_arcsec=None,
                t_solve_ms=None,
                t_extract_ms=None,
                raw={"reason": "need_at_least_4_stars"},
            )

        sorted_stars = sorted(stars, key=lambda s: s.flux, reverse=True)
        centroids = np.array([[s.y, s.x] for s in sorted_stars], dtype=np.float64)

        try:
            t3 = self._tetra()
            out = t3.solve_from_centroids(
                centroids,
                (height, width),
                fov_estimate=fov_est,
                fov_max_error=fov_err,
                solve_timeout=timeout,
            )
        except OSError as exc:
            return SolveResult(
                ra_deg=0.0,
                dec_deg=0.0,
                detected_stars=len(stars),
                solve_source=solve_source,
                status="DATABASE_ERROR",
                status_code=None,
                roll_deg=None,
                fov_deg=None,
                matches=None,
                prob=None,
                rmse_arcsec=None,
                t_solve_ms=None,
                t_extract_ms=None,
                raw={"error": str(exc)},
            )

        return _tetra_dict_to_result(out, len(stars), solve_source)

    def solve_from_bgr_frame(
        self,
        frame_bgr: np.ndarray,
        max_stars: int,
        hint_ra_deg: float = 0.0,
        hint_dec_deg: float = 0.0,
        solve_source: str = "full",
        fov_estimate: float | None = None,
        fov_max_error: float | None = None,
        solve_timeout_ms: int | None = None,
        max_image_side: int = 2048,
    ) -> SolveResult:
        """与 Tetra3 ``solve_from_image`` 等价：内置 ``get_centroids_from_image`` + ``solve_from_centroids``.

        Cedar-Solve / 官方示例走此提星链（局部背景减除、σ 阈值、连通域矩心），非 OpenCV OTSU。
        Same pipeline as Tetra3 ``solve_from_image`` (local bg, sigma threshold, scipy labeling).
        """
        del hint_ra_deg, hint_dec_deg
        from tetra3 import get_centroids_from_image  # noqa: PLC0415 — vendor path

        h0, w0 = frame_bgr.shape[:2]
        img = frame_bgr
        if max(h0, w0) > max_image_side:
            sc = max_image_side / float(max(h0, w0))
            img = cv2.resize(
                img,
                (max(1, int(w0 * sc)), max(1, int(h0 * sc))),
                interpolation=cv2.INTER_AREA,
            )
        height, width = int(img.shape[0]), int(img.shape[1])
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb)

        fov_est = float(fov_estimate if fov_estimate is not None else self.fov_deg)
        fov_err = fov_max_error if fov_max_error is not None else self.fov_max_error_deg
        timeout = float(
            solve_timeout_ms if solve_timeout_ms is not None else self.solve_timeout_ms
        )

        t0 = time.perf_counter()
        try:
            centroids = get_centroids_from_image(
                pil_image,
                max_returned=max_stars,
                filtsize=25,
                bg_sub_mode="local_mean",
                sigma_mode="global_root_square",
                sigma=2.0,
                binary_open=True,
                max_area=100,
                min_area=5,
            )
        except (OSError, ValueError, RuntimeError) as exc:
            return SolveResult(
                ra_deg=0.0,
                dec_deg=0.0,
                detected_stars=0,
                solve_source=solve_source,
                status="EXTRACTION_ERROR",
                status_code=None,
                roll_deg=None,
                fov_deg=None,
                matches=None,
                prob=None,
                rmse_arcsec=None,
                t_solve_ms=None,
                t_extract_ms=None,
                raw={"error": str(exc)},
            )
        t_extract_ms = (time.perf_counter() - t0) * 1000.0

        detected = int(len(centroids))
        if detected < 4:
            return SolveResult(
                ra_deg=0.0,
                dec_deg=0.0,
                detected_stars=detected,
                solve_source=solve_source,
                status="TOO_FEW",
                status_code=5,
                roll_deg=None,
                fov_deg=None,
                matches=None,
                prob=None,
                rmse_arcsec=None,
                t_solve_ms=None,
                t_extract_ms=t_extract_ms,
                raw={"reason": "need_at_least_4_stars"},
            )

        try:
            t3 = self._tetra()
            out = t3.solve_from_centroids(
                centroids,
                (height, width),
                fov_estimate=fov_est,
                fov_max_error=fov_err,
                solve_timeout=timeout,
            )
        except OSError as exc:
            return SolveResult(
                ra_deg=0.0,
                dec_deg=0.0,
                detected_stars=detected,
                solve_source=solve_source,
                status="DATABASE_ERROR",
                status_code=None,
                roll_deg=None,
                fov_deg=None,
                matches=None,
                prob=None,
                rmse_arcsec=None,
                t_solve_ms=None,
                t_extract_ms=t_extract_ms,
                raw={"error": str(exc)},
            )

        out["T_extract"] = t_extract_ms
        return _tetra_dict_to_result(out, detected, solve_source)


def _tetra_dict_to_result(
    out: dict[str, Any], detected_stars: int, solve_source: str
) -> SolveResult:
    """Tetra 返回 dict → SolveResult / Map Tetra output dict to SolveResult."""
    st = out.get("status")
    code = int(st) if st is not None else None
    name = _STATUS_NAMES.get(code, str(st)) if code is not None else "UNKNOWN"

    ra = out.get("RA")
    dec = out.get("Dec")
    ra_f = float(ra) if ra is not None else 0.0
    dec_f = float(dec) if dec is not None else 0.0

    raw = {k: v for k, v in out.items() if k not in ("RA", "Dec")}

    return SolveResult(
        ra_deg=ra_f,
        dec_deg=dec_f,
        detected_stars=detected_stars,
        solve_source=solve_source,
        status=name,
        status_code=code,
        roll_deg=_maybe_float(out.get("Roll")),
        fov_deg=_maybe_float(out.get("FOV")),
        matches=_maybe_int(out.get("Matches")),
        prob=_maybe_float(out.get("Prob")),
        rmse_arcsec=_maybe_float(out.get("RMSE")),
        t_solve_ms=_maybe_float(out.get("T_solve")),
        t_extract_ms=_maybe_float(out.get("T_extract")),
        raw=raw,
    )


def _maybe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _maybe_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
