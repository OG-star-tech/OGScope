"""
基于 Tetra3 (Cedar-Solve) 的星图解算 / Plate solving via Tetra3 (Cedar-Solve)
"""

from __future__ import annotations

import base64
import dataclasses
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from ogscope.algorithms.plate_solve.centroid_quality import filter_centroids_yx
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
class CentroidExtractionParams:
    """Tetra3 提星参数 / Parameters for get_centroids_from_image."""

    sigma: float = 2.5
    max_area: int = 400
    min_area: int = 5
    filtsize: int = 25
    binary_open: bool = True
    bg_sub_mode: str = "local_mean"
    sigma_mode: str = "global_root_square"
    max_axis_ratio: float | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> CentroidExtractionParams:
        """从应用配置构造 / Build from application settings."""
        return cls(
            sigma=settings.solver_centroid_sigma,
            max_area=settings.solver_centroid_max_area,
            min_area=settings.solver_centroid_min_area,
            filtsize=settings.solver_centroid_filtsize,
            binary_open=settings.solver_centroid_binary_open,
            bg_sub_mode=settings.solver_centroid_bg_sub_mode,
            sigma_mode=settings.solver_centroid_sigma_mode,
            max_axis_ratio=settings.solver_centroid_max_axis_ratio,
        )

    def to_get_centroids_kwargs(self) -> dict[str, Any]:
        """传给 get_centroids_from_image 的关键字 / Keyword args for Tetra3 centroiding."""
        kwargs: dict[str, Any] = {
            "filtsize": self.filtsize,
            "bg_sub_mode": self.bg_sub_mode,
            "sigma_mode": self.sigma_mode,
            "sigma": self.sigma,
            "binary_open": self.binary_open,
            "max_area": self.max_area,
            "min_area": self.min_area,
        }
        if self.max_axis_ratio is not None:
            kwargs["max_axis_ratio"] = self.max_axis_ratio
        return kwargs


def merge_centroid_params(
    base: CentroidExtractionParams,
    overrides: dict[str, Any],
) -> CentroidExtractionParams:
    """用非 None 字段覆盖 base / Overlay non-None keys onto base."""
    allowed = {f.name for f in dataclasses.fields(CentroidExtractionParams)}
    filtered = {k: v for k, v in overrides.items() if k in allowed and v is not None}
    return dataclasses.replace(base, **filtered)


def resize_bgr_for_extraction(
    frame_bgr: np.ndarray, max_image_side: int
) -> tuple[np.ndarray, tuple[int, int]]:
    """与解算相同的缩放，返回 (BGR, 原始高宽) / Same resize as solve; returns BGR and original shape."""
    h0, w0 = int(frame_bgr.shape[0]), int(frame_bgr.shape[1])
    img = frame_bgr
    if max(h0, w0) > max_image_side:
        sc = max_image_side / float(max(h0, w0))
        img = cv2.resize(
            frame_bgr,
            (max(1, int(w0 * sc)), max(1, int(h0 * sc))),
            interpolation=cv2.INTER_AREA,
        )
    return img, (h0, w0)


def subtract_large_scale_background_bgr(
    frame_bgr: np.ndarray,
    *,
    downsample_max_side: int,
) -> np.ndarray:
    """低分辨率估计大尺度背景并做亮度校正，减轻角部光晕等渐变 / Fast large-scale flat removal.

    在小图上高斯平滑得到低频背景，上采样后与灰度相减，再按比例映射回 BGR，便于 Tetra3 提星。
    Estimates low-frequency background on a downscaled image, subtracts in luminance, scales RGB.
    """
    if frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3:
        return frame_bgr
    h, w = int(frame_bgr.shape[0]), int(frame_bgr.shape[1])
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    side = max(h, w)
    sc = min(1.0, float(downsample_max_side) / float(side))
    sw = max(1, int(round(w * sc)))
    sh = max(1, int(round(h * sc)))
    small = cv2.resize(gray, (sw, sh), interpolation=cv2.INTER_AREA)
    sigma_s = max(2.0, float(min(sw, sh)) / 32.0)
    bg_small = cv2.GaussianBlur(small, (0, 0), sigmaX=sigma_s, sigmaY=sigma_s)
    bg = cv2.resize(bg_small, (w, h), interpolation=cv2.INTER_LINEAR).astype(np.float32)
    mean_gray = float(np.mean(gray))
    # 复用背景数组承载校正亮度和比例，减少两张全画幅float32临时图
    # Reuse the background buffer for corrected luminance and ratio to drop two float32 frames.
    np.subtract(gray, bg, out=bg)
    bg += mean_gray
    np.clip(bg, 1e-3, 255.0, out=bg)
    np.maximum(gray, 1e-3, out=gray)
    np.divide(bg, gray, out=bg)
    np.clip(bg, 0.0, 4.0, out=bg)
    out = frame_bgr.astype(np.float32) * bg[..., np.newaxis]
    return np.clip(np.round(out), 0, 255).astype(np.uint8)


def centroid_extraction_preview(
    frame_bgr: np.ndarray,
    *,
    max_stars: int,
    centroid_params: CentroidExtractionParams,
    max_image_side: int,
    large_scale_bg_subtract: bool = False,
    downsample_max_side: int = 256,
) -> dict[str, Any]:
    """提星预览：二值掩膜 PNG（base64），不解算 Tetra3 / Preview extraction mask without plate solve."""
    from tetra3 import get_centroids_from_image  # noqa: PLC0415

    img, (h0, w0) = resize_bgr_for_extraction(frame_bgr, max_image_side)
    if large_scale_bg_subtract:
        img = subtract_large_scale_background_bgr(
            img, downsample_max_side=downsample_max_side
        )
    height, width = int(img.shape[0]), int(img.shape[1])
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    pil_image = Image.fromarray(rgb)
    kwargs = centroid_params.to_get_centroids_kwargs()
    t0 = time.perf_counter()
    try:
        centroids, images_dict = get_centroids_from_image(
            pil_image,
            max_returned=max_stars,
            return_images=True,
            **kwargs,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        return {
            "success": False,
            "error": str(exc),
            "detected_stars": 0,
            "t_extract_ms": None,
            "binary_mask_png_base64": None,
            "solve_width": width,
            "solve_height": height,
            "original_width": w0,
            "original_height": h0,
        }
    t_extract_ms = (time.perf_counter() - t0) * 1000.0
    detected = int(len(centroids))
    mask = images_dict.get("binary_mask")
    b64: str | None = None
    if mask is not None:
        mask_u8 = (np.asarray(mask, dtype=np.uint8) * 255).astype(np.uint8)
        ok, buf = cv2.imencode(".png", mask_u8)
        if ok:
            b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    return {
        "success": True,
        "detected_stars": detected,
        "t_extract_ms": round(t_extract_ms, 3),
        "binary_mask_png_base64": b64,
        "solve_width": width,
        "solve_height": height,
        "original_width": w0,
        "original_height": h0,
    }


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
    t_preprocess_ms: float | None
    large_scale_bg_subtract: bool = False
    raw: dict[str, Any] = field(default_factory=dict)
    # 原图像素系下的叠加数据（与 Canvas x,y 一致）/ Overlay in original image pixels (Canvas x,y)
    solve_overlay: dict[str, Any] | None = None
    # 质心质量过滤（过密/共线）/ Centroid quality (dense + collinear)
    centroid_quality: dict[str, Any] | None = None

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
            "t_preprocess_ms": self.t_preprocess_ms,
            "large_scale_bg_subtract": self.large_scale_bg_subtract,
        }
        if self.centroid_quality is not None:
            base["centroid_quality"] = _json_safe(self.centroid_quality)
        if self.solve_overlay is not None:
            base["solve_overlay"] = _json_safe(self.solve_overlay)
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
        centroid_rejection_level: int = 3,
    ) -> SolveResult:
        """解算画面中心赤道坐标 / Solve frame center RA/Dec.

        hint_ra_deg / hint_dec_deg 对 Tetra3 无影响，仅保留 API 兼容 / Hints ignored by Tetra3.
        """
        del hint_ra_deg, hint_dec_deg
        height, width = int(frame_shape[0]), int(frame_shape[1])
        level = max(1, min(5, int(centroid_rejection_level)))
        fov_est = float(fov_estimate if fov_estimate is not None else self.fov_deg)
        fov_err = fov_max_error if fov_max_error is not None else self.fov_max_error_deg
        timeout = float(
            solve_timeout_ms if solve_timeout_ms is not None else self.solve_timeout_ms
        )

        if len(stars) < 4:
            sorted_stars = sorted(stars, key=lambda s: s.flux, reverse=True)
            cyx = np.array([[s.y, s.x] for s in sorted_stars], dtype=np.float64)
            overlay = (
                _make_solve_overlay({}, cyx, None, (height, width), (height, width))
                if len(cyx) > 0
                else None
            )
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
                t_preprocess_ms=None,
                large_scale_bg_subtract=False,
                raw={"reason": "need_at_least_4_stars"},
                solve_overlay=overlay,
            )

        sorted_stars = sorted(stars, key=lambda s: s.flux, reverse=True)
        centroids = np.array([[s.y, s.x] for s in sorted_stars], dtype=np.float64)
        centroids, cq = filter_centroids_yx(centroids, (height, width), level)
        if centroids.shape[0] < 4:
            overlay = (
                _make_solve_overlay(
                    {}, centroids, None, (height, width), (height, width)
                )
                if len(centroids) > 0
                else None
            )
            return SolveResult(
                ra_deg=0.0,
                dec_deg=0.0,
                detected_stars=int(centroids.shape[0]),
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
                t_preprocess_ms=None,
                large_scale_bg_subtract=False,
                raw={"reason": "too_few_after_centroid_filter"},
                solve_overlay=overlay,
                centroid_quality=cq,
            )

        try:
            t3 = self._tetra()
            out = t3.solve_from_centroids(
                centroids,
                (height, width),
                fov_estimate=fov_est,
                fov_max_error=fov_err,
                solve_timeout=timeout,
                return_matches=True,
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
                t_preprocess_ms=None,
                large_scale_bg_subtract=False,
                raw={"error": str(exc)},
            )

        return _tetra_dict_to_result(
            out,
            int(centroids.shape[0]),
            solve_source,
            centroids_yx=centroids,
            frame_shape_original=(height, width),
            solve_shape=(height, width),
            centroid_quality=cq,
        )

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
        max_image_side: int | None = None,
        centroid_params: CentroidExtractionParams | None = None,
        large_scale_bg_subtract: bool = False,
        centroid_rejection_level: int = 3,
    ) -> SolveResult:
        """与 Tetra3 ``solve_from_image`` 等价：内置 ``get_centroids_from_image`` + ``solve_from_centroids``.

        Cedar-Solve / 官方示例走此提星链（局部背景减除、σ 阈值、连通域矩心），非 OpenCV OTSU。
        Same pipeline as Tetra3 ``solve_from_image`` (local bg, sigma threshold, scipy labeling).
        可选在提星前做大尺度背景减除（角部光晕等）/ Optional large-scale BG flattening before centroiding.
        """
        del hint_ra_deg, hint_dec_deg
        from tetra3 import get_centroids_from_image  # noqa: PLC0415 — vendor path

        settings = get_settings()
        side_cap = (
            int(max_image_side)
            if max_image_side is not None
            else int(settings.solver_max_image_side)
        )
        if settings.solver_max_image_side_hard_cap is not None:
            side_cap = min(side_cap, int(settings.solver_max_image_side_hard_cap))
        side_cap = max(256, int(side_cap))
        level = max(1, min(5, int(centroid_rejection_level)))
        max_stars = max(4, int(max_stars))
        if settings.solver_max_stars_hard_cap is not None:
            max_stars = min(max_stars, int(settings.solver_max_stars_hard_cap))
        params = (
            centroid_params
            if centroid_params is not None
            else CentroidExtractionParams.from_settings(settings)
        )
        t0_preprocess = time.perf_counter()
        img, (h0, w0) = resize_bgr_for_extraction(frame_bgr, side_cap)
        if large_scale_bg_subtract:
            img = subtract_large_scale_background_bgr(
                img,
                downsample_max_side=int(settings.solver_large_scale_bg_downsample),
            )
        height, width = int(img.shape[0]), int(img.shape[1])
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb)
        t_preprocess_ms = (time.perf_counter() - t0_preprocess) * 1000.0

        fov_est = float(fov_estimate if fov_estimate is not None else self.fov_deg)
        fov_err = fov_max_error if fov_max_error is not None else self.fov_max_error_deg
        timeout = float(
            solve_timeout_ms if solve_timeout_ms is not None else self.solve_timeout_ms
        )

        centroid_kw = params.to_get_centroids_kwargs()
        t0 = time.perf_counter()
        try:
            centroids = get_centroids_from_image(
                pil_image,
                max_returned=max_stars,
                **centroid_kw,
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
                t_preprocess_ms=t_preprocess_ms,
                large_scale_bg_subtract=large_scale_bg_subtract,
                raw={"error": str(exc)},
            )
        t_extract_ms = (time.perf_counter() - t0) * 1000.0

        detected_raw = int(len(centroids))
        cyx = np.asarray(centroids, dtype=np.float64)
        if detected_raw >= 4:
            cyx_f, cq = filter_centroids_yx(cyx, (height, width), level)
        else:
            cyx_f, cq = cyx, {
                "level": level,
                "flags": [],
                "hints": [],
                "metrics": {
                    "input_count": detected_raw,
                    "output_count": detected_raw,
                    "removed_dense": 0,
                    "removed_line": 0,
                },
            }
        detected = int(cyx_f.shape[0])
        if detected < 4:
            overlay = (
                _make_solve_overlay({}, cyx_f, None, (h0, w0), (height, width))
                if len(cyx_f) > 0
                else None
            )
            raw_ex: dict[str, Any] = {"reason": "need_at_least_4_stars"}
            if detected_raw >= 4 and detected < 4:
                raw_ex["reason"] = "too_few_after_centroid_filter"
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
                t_preprocess_ms=t_preprocess_ms,
                large_scale_bg_subtract=large_scale_bg_subtract,
                raw=raw_ex,
                solve_overlay=overlay,
                centroid_quality=cq,
            )

        try:
            t3 = self._tetra()
            out = t3.solve_from_centroids(
                cyx_f,
                (height, width),
                fov_estimate=fov_est,
                fov_max_error=fov_err,
                solve_timeout=timeout,
                return_matches=True,
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
                t_preprocess_ms=t_preprocess_ms,
                large_scale_bg_subtract=large_scale_bg_subtract,
                raw={"error": str(exc)},
                centroid_quality=cq,
            )

        out["T_extract"] = t_extract_ms
        out["T_preprocess"] = t_preprocess_ms
        return _tetra_dict_to_result(
            out,
            detected,
            solve_source,
            centroids_yx=cyx_f,
            frame_shape_original=(h0, w0),
            solve_shape=(height, width),
            large_scale_bg_subtract=large_scale_bg_subtract,
            centroid_quality=cq,
        )


def _make_solve_overlay(
    tetra_out: dict[str, Any],
    centroids_yx: np.ndarray,
    rejected_centroids_yx: np.ndarray | None,
    frame_shape_original: tuple[int, int],
    solve_shape: tuple[int, int],
) -> dict[str, Any] | None:
    """从 Tetra 输出与质心构造 solve_overlay（原图 x,y 像素）/ Build solve_overlay in original pixels."""
    h0, w0 = int(frame_shape_original[0]), int(frame_shape_original[1])
    h1, w1 = int(solve_shape[0]), int(solve_shape[1])
    if h1 <= 0 or w1 <= 0:
        return None
    sx = w0 / float(w1)
    sy = h0 / float(h1)

    stars_all: list[dict[str, float]] = []
    arr = np.asarray(centroids_yx, dtype=np.float64)
    if arr.size > 0 and arr.ndim == 2 and arr.shape[1] >= 2:
        for row in arr:
            y_s, x_s = float(row[0]), float(row[1])
            stars_all.append({"x": x_s * sx, "y": y_s * sy})
    stars_rejected: list[dict[str, float]] = []
    rej = np.asarray(rejected_centroids_yx, dtype=np.float64)
    if rej.size > 0 and rej.ndim == 2 and rej.shape[1] >= 2:
        for row in rej:
            y_s, x_s = float(row[0]), float(row[1])
            stars_rejected.append({"x": x_s * sx, "y": y_s * sy})

    stars_matched: list[dict[str, Any]] = []
    raw_matched = tetra_out.get("matched_centroids")
    raw_catalog = tetra_out.get("matched_stars")
    raw_cat_ids = tetra_out.get("matched_catID")
    if raw_matched:
        for i, mc in enumerate(raw_matched):
            y_s, x_s = float(mc[0]), float(mc[1])
            entry: dict[str, Any] = {"x": x_s * sx, "y": y_s * sy}
            if raw_catalog is not None and i < len(raw_catalog):
                ms = raw_catalog[i]
                entry["ra_deg"] = float(ms[0])
                entry["dec_deg"] = float(ms[1])
                entry["mag"] = float(ms[2])
            if raw_cat_ids is not None and i < len(raw_cat_ids):
                cid = raw_cat_ids[i]
                entry["cat_id"] = _json_safe(cid) if cid is not None else None
            stars_matched.append(entry)

    stars_pattern: list[dict[str, float]] = []
    raw_pat = tetra_out.get("pattern_centroids")
    if raw_pat:
        for pc in raw_pat:
            y_s, x_s = float(pc[0]), float(pc[1])
            stars_pattern.append({"x": x_s * sx, "y": y_s * sy})

    return {
        "frame_shape": [h0, w0],
        "stars_matched": stars_matched,
        "stars_pattern": stars_pattern,
        "stars_all_centroids": stars_all,
        "stars_rejected_centroids": stars_rejected,
    }


def _tetra_dict_to_result(
    out: dict[str, Any],
    detected_stars: int,
    solve_source: str,
    *,
    centroids_yx: np.ndarray | None = None,
    frame_shape_original: tuple[int, int] | None = None,
    solve_shape: tuple[int, int] | None = None,
    large_scale_bg_subtract: bool = False,
    centroid_quality: dict[str, Any] | None = None,
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

    overlay: dict[str, Any] | None = None
    rejected_yx: np.ndarray | None = None
    if centroid_quality and isinstance(centroid_quality, dict):
        rejected_raw = centroid_quality.get("rejected_centroids_yx")
        if isinstance(rejected_raw, list):
            try:
                tmp = np.asarray(rejected_raw, dtype=np.float64)
                if tmp.ndim == 2 and tmp.shape[1] >= 2 and tmp.size > 0:
                    rejected_yx = tmp[:, :2]
            except (TypeError, ValueError):
                rejected_yx = None
    if (
        centroids_yx is not None
        and frame_shape_original is not None
        and solve_shape is not None
    ):
        overlay = _make_solve_overlay(
            out, centroids_yx, rejected_yx, frame_shape_original, solve_shape
        )

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
        t_preprocess_ms=_maybe_float(out.get("T_preprocess")),
        large_scale_bg_subtract=large_scale_bg_subtract,
        raw=raw,
        solve_overlay=overlay,
        centroid_quality=centroid_quality,
    )


def warmup_tetra3() -> None:
    """预热 Tetra3 单例与数据库，降低首轮解算延迟 / Warm up Tetra3 singleton to reduce first-solve latency."""
    _get_tetra3(get_settings())


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
