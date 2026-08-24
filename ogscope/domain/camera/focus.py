"""星点焦点质量测量 / Star focus quality measurement."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from ogscope.algorithms.star_extract import StarExtractor


@dataclass(slots=True)
class FocusStarMetric:
    """单颗星点的焦点指标 / Focus metrics for one detected star."""

    x: float
    y: float
    hfd_px: float
    fwhm_px: float
    snr: float
    roundness: float
    concentration: float
    peak: float
    flux: float
    saturated: bool

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 友好的数值 / Return JSON-friendly values."""
        payload = asdict(self)
        for key, value in payload.items():
            if isinstance(value, float):
                payload[key] = round(value, 4)
        return payload


class FocusMetricAnalyzer:
    """在原始相机帧上测量 HFD 与辅助质量指标 / Measure HFD on raw frames."""

    def __init__(
        self,
        *,
        max_stars: int = 40,
        stamp_radius: int = 24,
        min_snr: float = 8.0,
        min_roundness: float = 0.35,
    ) -> None:
        self._extractor = StarExtractor(max_stars=max_stars)
        self._stamp_radius = max(8, int(stamp_radius))
        self._min_snr = float(min_snr)
        self._min_roundness = float(min_roundness)

    @staticmethod
    def _gray(frame: np.ndarray) -> np.ndarray:
        """兼容灰度、RGB 与 RGBA 帧 / Accept grayscale, RGB, and RGBA frames."""
        data = np.asarray(frame)
        if data.ndim == 2:
            return data.astype(np.float32, copy=False)
        if data.ndim == 3 and data.shape[2] >= 3:
            # 通道均值不依赖 RGB/BGR 顺序 / Channel mean is RGB/BGR agnostic.
            return np.mean(data[..., :3], axis=2, dtype=np.float32)
        raise ValueError("unsupported focus frame shape / 不支持的焦点分析帧形状")

    def _measure_star(
        self,
        gray: np.ndarray,
        *,
        x: float,
        y: float,
        saturation_level: float,
    ) -> FocusStarMetric | None:
        radius = self._stamp_radius
        cx = int(round(x))
        cy = int(round(y))
        h, w = gray.shape
        if cx - radius < 0 or cy - radius < 0:
            return None
        if cx + radius >= w or cy + radius >= h:
            return None

        stamp = gray[cy - radius : cy + radius + 1, cx - radius : cx + radius + 1]
        yy, xx = np.indices(stamp.shape, dtype=np.float32)
        local_center = float(radius)
        initial_r = np.hypot(xx - local_center, yy - local_center)
        background_pixels = stamp[initial_r >= radius * 0.78]
        if background_pixels.size == 0:
            return None
        background = float(np.median(background_pixels))
        mad = float(np.median(np.abs(background_pixels - background)))
        noise = max(1.0, 1.4826 * mad)
        # 阈值化并限制测光孔径，避免暗场正噪声在大窗口内累积后淹没星点轮廓。
        # Threshold and limit the aperture so positive dark-field noise cannot dominate the stellar profile.
        signal = np.clip(stamp - background - 1.5 * noise, 0.0, None)
        signal[initial_r > radius * 0.65] = 0.0
        total_flux = float(np.sum(signal))
        peak = float(np.max(stamp))
        peak_signal = max(0.0, peak - background)
        if total_flux <= 0.0 or peak_signal < max(4.0 * noise, 3.0):
            return None

        centroid_x = float(np.sum(signal * xx) / total_flux)
        centroid_y = float(np.sum(signal * yy) / total_flux)
        dx = xx - centroid_x
        dy = yy - centroid_y
        radial = np.hypot(dx, dy)
        order = np.argsort(radial, axis=None)
        sorted_radius = radial.ravel()[order]
        cumulative = np.cumsum(signal.ravel()[order])
        half_index = int(np.searchsorted(cumulative, total_flux * 0.5, side="left"))
        half_index = min(half_index, sorted_radius.size - 1)
        hfd = 2.0 * float(sorted_radius[half_index])

        var_x = float(np.sum(signal * dx * dx) / total_flux)
        var_y = float(np.sum(signal * dy * dy) / total_flux)
        sigma_x = float(np.sqrt(max(0.0, var_x)))
        sigma_y = float(np.sqrt(max(0.0, var_y)))
        sigma_major = max(sigma_x, sigma_y)
        sigma_minor = min(sigma_x, sigma_y)
        roundness = sigma_minor / sigma_major if sigma_major > 1e-6 else 1.0
        fwhm = 2.35482 * float(np.sqrt(max(0.0, (var_x + var_y) / 2.0)))

        core_flux = float(np.sum(signal[radial <= 1.5]))
        reference_flux = float(np.sum(signal[radial <= 4.5]))
        concentration = core_flux / reference_flux if reference_flux > 0.0 else 0.0
        aperture_pixels = max(1, int(np.count_nonzero(radial <= radius * 0.72)))
        snr = total_flux / float(
            np.sqrt(max(total_flux, 0.0) + aperture_pixels * noise**2)
        )
        saturated = peak >= saturation_level * 0.98

        return FocusStarMetric(
            x=x,
            y=y,
            hfd_px=hfd,
            fwhm_px=fwhm,
            snr=snr,
            roundness=roundness,
            concentration=concentration,
            peak=peak,
            flux=total_flux,
            saturated=saturated,
        )

    def analyze(
        self,
        frame: np.ndarray,
        *,
        frame_id: int,
        timestamp: float,
        target_x: float | None = None,
        target_y: float | None = None,
    ) -> dict[str, Any]:
        """分析一帧并返回多星稳健统计 / Analyze one frame with robust multi-star statistics."""
        raw = np.asarray(frame)
        gray = self._gray(raw)
        h, w = gray.shape
        if np.issubdtype(raw.dtype, np.integer):
            saturation_level = float(np.iinfo(raw.dtype).max)
        else:
            # 浮点帧通常仍使用 0..1 或 0..255 标度；不能把当前帧峰值当作饱和上限。
            # Float frames commonly use 0..1 or 0..255; the current peak is not a saturation ceiling.
            frame_peak = float(np.max(gray))
            saturation_level = 1.0 if frame_peak <= 1.5 else 255.0

        candidates = self._extractor.extract(raw)
        measured: list[FocusStarMetric] = []
        for candidate in candidates:
            metric = self._measure_star(
                gray,
                x=float(candidate.x),
                y=float(candidate.y),
                saturation_level=saturation_level,
            )
            if metric is not None:
                measured.append(metric)

        usable = [
            star
            for star in measured
            if not star.saturated
            and star.snr >= self._min_snr
            and star.roundness >= self._min_roundness
            and 0.2 <= star.hfd_px <= self._stamp_radius * 1.8
        ]
        usable.sort(key=lambda star: star.snr, reverse=True)
        usable = usable[:20]

        warnings: list[str] = []
        if not candidates:
            warnings.append("no_stars_detected")
        if any(star.saturated for star in measured):
            warnings.append("saturated_stars_rejected")
        if candidates and not usable:
            warnings.append("no_usable_stars")
        elif len(usable) < 3:
            warnings.append("low_star_count")

        selected: FocusStarMetric | None = None
        if usable and target_x is not None and target_y is not None:
            target_px_x = min(1.0, max(0.0, float(target_x))) * max(0, w - 1)
            target_px_y = min(1.0, max(0.0, float(target_y))) * max(0, h - 1)
            nearest = min(
                usable,
                key=lambda star: (star.x - target_px_x) ** 2
                + (star.y - target_px_y) ** 2,
            )
            max_distance = max(32.0, min(h, w) * 0.12)
            distance = float(np.hypot(nearest.x - target_px_x, nearest.y - target_px_y))
            if distance <= max_distance:
                selected = nearest
            else:
                warnings.append("target_star_not_found")
        elif usable:
            selected = usable[0]

        state = "measuring"
        if not usable:
            state = "no_stars"
        elif len(usable) < 3:
            state = "low_confidence"

        aggregate: dict[str, float] | None = None
        if usable:
            hfd_values = np.asarray([star.hfd_px for star in usable], dtype=np.float64)
            fwhm_values = np.asarray(
                [star.fwhm_px for star in usable], dtype=np.float64
            )
            concentration_values = np.asarray(
                [star.concentration for star in usable], dtype=np.float64
            )
            median_hfd = float(np.median(hfd_values))
            aggregate = {
                "median_hfd_px": round(median_hfd, 4),
                "hfd_mad_px": round(
                    float(np.median(np.abs(hfd_values - median_hfd))), 4
                ),
                "median_fwhm_px": round(float(np.median(fwhm_values)), 4),
                "median_concentration": round(
                    float(np.median(concentration_values)), 4
                ),
            }

        return {
            "success": True,
            "state": state,
            "frame_id": int(frame_id),
            "timestamp": float(timestamp),
            "frame": {"width": int(w), "height": int(h)},
            "stars_detected": len(candidates),
            "stars_measured": len(measured),
            "stars_used": len(usable),
            "aggregate": aggregate,
            "selected_star": selected.to_dict() if selected is not None else None,
            "stars": [star.to_dict() for star in usable],
            "warnings": warnings,
        }


focus_metric_analyzer = FocusMetricAnalyzer()


__all__ = ["FocusMetricAnalyzer", "FocusStarMetric", "focus_metric_analyzer"]
