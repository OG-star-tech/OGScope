"""星点焦点质量测量 / Star focus quality measurement."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import cv2
import numpy as np


@dataclass(slots=True)
class FocusCandidate:
    """焦点测量候选亮点 / Candidate point source for focus measurement."""

    x: float
    y: float
    flux: float
    area: int
    source: str = "auto"


class FocusCandidateExtractor:
    """用局部背景与噪声阈值保留欠采样星点 / Keep undersampled stars with local statistics."""

    def __init__(
        self,
        *,
        max_stars: int = 40,
        filter_size: int = 25,
        threshold_sigma: float = 2.5,
        max_area: int = 400,
    ) -> None:
        self._max_stars = max(1, int(max_stars))
        size = max(7, int(filter_size))
        self._filter_size = size if size % 2 else size + 1
        self._threshold_sigma = max(1.5, float(threshold_sigma))
        self._max_area = max(16, int(max_area))

    def extract(self, gray: np.ndarray) -> tuple[list[FocusCandidate], dict[str, Any]]:
        """提取小而亮的连通域且不做形态学开运算 / Extract compact sources without opening."""
        data = np.asarray(gray, dtype=np.float32)
        background = cv2.blur(
            data,
            (self._filter_size, self._filter_size),
            borderType=cv2.BORDER_REFLECT,
        )
        residual = data - background
        residual_median = float(np.median(residual))
        mad = float(np.median(np.abs(residual - residual_median)))
        noise = max(0.5, 1.4826 * mad)
        threshold = max(1.5, self._threshold_sigma * noise)
        mask = np.asarray(residual > threshold, dtype=np.uint8)

        count, labels, stats, centroids = cv2.connectedComponentsWithStats(
            mask, connectivity=8
        )
        positive = np.clip(residual, 0.0, None)
        flat_labels = labels.ravel()
        flux_by_label = np.bincount(
            flat_labels,
            weights=positive.ravel(),
            minlength=count,
        )
        peak_by_label = np.full(count, -np.inf, dtype=np.float32)
        np.maximum.at(peak_by_label, flat_labels, residual.ravel())
        candidates: list[FocusCandidate] = []
        rejected_large = 0
        rejected_weak = 0
        for label in range(1, count):
            area = int(stats[label, cv2.CC_STAT_AREA])
            if area > self._max_area:
                rejected_large += 1
                continue
            flux = float(flux_by_label[label])
            peak = float(peak_by_label[label])
            # 单像素候选需要更高峰值，降低热像素/随机噪声排序权重，但不直接删除。
            # Single-pixel candidates need a stronger peak, reducing noise/hot-pixel priority without an opening.
            min_peak_sigma = 4.5 if area <= 1 else 3.0
            if flux <= 0.0 or peak < max(2.0, min_peak_sigma * noise):
                rejected_weak += 1
                continue
            cx = float(centroids[label, 0])
            cy = float(centroids[label, 1])
            candidates.append(
                FocusCandidate(x=cx, y=cy, flux=flux, area=area, source="auto")
            )

        candidates.sort(key=lambda item: item.flux, reverse=True)
        return candidates[: self._max_stars], {
            "pipeline": "focus_local_sigma_v1",
            "noise_sigma": round(noise, 4),
            "threshold": round(threshold, 4),
            "components": max(0, count - 1),
            "rejected_large": rejected_large,
            "rejected_weak": rejected_weak,
        }


@dataclass(slots=True)
class FocusStarMetric:
    """单颗星点的焦点指标 / Focus metrics for one detected star."""

    x: float
    y: float
    hfd_px: float
    fwhm_px: float
    snr: float
    peak_snr: float
    roundness: float
    concentration: float
    aperture_radius_px: float
    peak: float
    flux: float
    saturated: bool
    undersampled: bool
    source: str

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
        min_snr: float = 4.0,
        min_peak_snr: float = 5.0,
        min_roundness: float = 0.2,
    ) -> None:
        self._extractor = FocusCandidateExtractor(max_stars=max_stars)
        self._stamp_radius = max(8, int(stamp_radius))
        self._min_snr = float(min_snr)
        self._min_peak_snr = float(min_peak_snr)
        self._min_roundness = float(min_roundness)

    @staticmethod
    def _gray(frame: np.ndarray) -> np.ndarray:
        """兼容灰度、RGB 与 RGBA 帧 / Accept grayscale, RGB, and RGBA frames."""
        data = np.asarray(frame)
        if data.ndim == 2:
            return data.astype(np.float32, copy=False)
        if data.ndim == 3 and data.shape[2] >= 3:
            # 相机主流是 RGB888；显式使用 RGB 亮度，避免压低偏红星点。
            # The main stream is RGB888; explicit RGB luminance avoids dimming red stars.
            rgb = data[..., :3].astype(np.float32, copy=False)
            return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114
        raise ValueError("unsupported focus frame shape / 不支持的焦点分析帧形状")

    @staticmethod
    def _target_candidate(
        gray: np.ndarray, *, target_x: float, target_y: float
    ) -> FocusCandidate | None:
        """在点击位置附近直接找局部峰值 / Find a local peak near the clicked target."""
        h, w = gray.shape
        px = min(1.0, max(0.0, float(target_x))) * max(0, w - 1)
        py = min(1.0, max(0.0, float(target_y))) * max(0, h - 1)
        radius = max(8, min(24, int(round(min(h, w) * 0.025))))
        x0 = max(0, int(round(px)) - radius)
        x1 = min(w, int(round(px)) + radius + 1)
        y0 = max(0, int(round(py)) - radius)
        y1 = min(h, int(round(py)) + radius + 1)
        roi = np.asarray(gray[y0:y1, x0:x1], dtype=np.float32)
        if roi.size == 0:
            return None
        background = float(np.median(roi))
        mad = float(np.median(np.abs(roi - background)))
        noise = max(0.5, 1.4826 * mad)
        index = int(np.argmax(roi))
        iy, ix = np.unravel_index(index, roi.shape)
        peak_signal = float(roi[iy, ix] - background)
        if peak_signal < max(2.0, 3.5 * noise):
            return None
        return FocusCandidate(
            x=float(x0 + ix),
            y=float(y0 + iy),
            flux=peak_signal,
            area=1,
            source="target",
        )

    def _measure_star(
        self,
        gray: np.ndarray,
        *,
        x: float,
        y: float,
        saturation_level: float,
        source: str,
    ) -> tuple[FocusStarMetric | None, str | None]:
        radius = self._stamp_radius
        cx = int(round(x))
        cy = int(round(y))
        h, w = gray.shape
        if cx - radius < 0 or cy - radius < 0:
            return None, "edge"
        if cx + radius >= w or cy + radius >= h:
            return None, "edge"

        stamp = gray[cy - radius : cy + radius + 1, cx - radius : cx + radius + 1]
        yy, xx = np.indices(stamp.shape, dtype=np.float32)
        local_center = float(radius)
        initial_r = np.hypot(xx - local_center, yy - local_center)
        background_pixels = stamp[initial_r >= radius * 0.78]
        if background_pixels.size == 0:
            return None, "background"
        background = float(np.median(background_pixels))
        mad = float(np.median(np.abs(background_pixels - background)))
        noise = max(0.5, 1.4826 * mad)
        residual = stamp - background

        # 候选矩心可能偏离亚像素峰值；在小邻域内重新居中。
        # Recenter on the local peak because a tiny connected-component centroid may be fractional.
        search_radius = min(5, radius // 2)
        centre_slice = residual[
            radius - search_radius : radius + search_radius + 1,
            radius - search_radius : radius + search_radius + 1,
        ]
        peak_index = int(np.argmax(centre_slice))
        peak_y, peak_x = np.unravel_index(peak_index, centre_slice.shape)
        peak_x = int(peak_x + radius - search_radius)
        peak_y = int(peak_y + radius - search_radius)
        radial_from_peak = np.hypot(xx - float(peak_x), yy - float(peak_y))
        peak_signal = max(0.0, float(residual[peak_y, peak_x]))
        if peak_signal < max(3.5 * noise, 2.0):
            return None, "low_peak"

        # 用显著连通域估计星点尺寸，再选择 3..10 px 自适应孔径。
        # Estimate source extent from the significant component, then use a 3..10 px aperture.
        core_mask = np.asarray(
            (residual >= max(noise, 0.75)) & (radial_from_peak <= 10.0),
            dtype=np.uint8,
        )
        component_count, component_labels = cv2.connectedComponents(
            core_mask, connectivity=8
        )
        peak_label = int(component_labels[peak_y, peak_x])
        if component_count <= 1 or peak_label <= 0:
            component_radius = 0.0
        else:
            component_radius = float(
                np.max(radial_from_peak[component_labels == peak_label])
            )
        aperture_radius = float(np.clip(component_radius + 2.0, 3.0, 10.0))
        aperture_mask = radial_from_peak <= aperture_radius
        signal = np.clip(residual - 0.5 * noise, 0.0, None)
        signal[~aperture_mask] = 0.0
        signal[residual < 0.75 * noise] = 0.0
        total_flux = float(np.sum(signal))
        peak = float(np.max(stamp))
        if total_flux <= 0.0:
            return None, "empty_flux"

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
        aperture_pixels = max(1, int(np.count_nonzero(aperture_mask)))
        snr = total_flux / float(
            np.sqrt(max(total_flux, 0.0) + aperture_pixels * noise**2)
        )
        peak_snr = peak_signal / noise
        saturated = peak >= saturation_level * 0.98
        undersampled = hfd < 1.0 or fwhm < 1.0

        return (
            FocusStarMetric(
                x=float(cx - radius + centroid_x),
                y=float(cy - radius + centroid_y),
                hfd_px=hfd,
                fwhm_px=fwhm,
                snr=snr,
                peak_snr=peak_snr,
                roundness=roundness,
                concentration=concentration,
                aperture_radius_px=aperture_radius,
                peak=peak,
                flux=total_flux,
                saturated=saturated,
                undersampled=undersampled,
                source=source,
            ),
            None,
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

        candidates, detection = self._extractor.extract(gray)
        target_candidate: FocusCandidate | None = None
        if target_x is not None and target_y is not None:
            target_candidate = self._target_candidate(
                gray, target_x=target_x, target_y=target_y
            )
            if target_candidate is not None:
                candidates = [
                    candidate
                    for candidate in candidates
                    if (candidate.x - target_candidate.x) ** 2
                    + (candidate.y - target_candidate.y) ** 2
                    >= 16.0
                ]
                candidates.insert(0, target_candidate)
        detection["target_forced"] = target_candidate is not None

        measured: list[FocusStarMetric] = []
        measurement_rejections: dict[str, int] = {}
        for candidate in candidates:
            metric, rejection = self._measure_star(
                gray,
                x=float(candidate.x),
                y=float(candidate.y),
                saturation_level=saturation_level,
                source=candidate.source,
            )
            if metric is not None:
                measured.append(metric)
            elif rejection is not None:
                measurement_rejections[rejection] = (
                    measurement_rejections.get(rejection, 0) + 1
                )

        usable: list[FocusStarMetric] = []
        quality_rejections: dict[str, int] = {}
        for star in measured:
            reason: str | None = None
            if star.saturated:
                reason = "saturated"
            elif (
                star.source == "auto"
                and star.fwhm_px < 0.35
                and star.concentration >= 0.995
            ):
                reason = "hot_pixel_like"
            elif star.peak_snr < self._min_peak_snr:
                reason = "low_peak_snr"
            elif star.snr < self._min_snr:
                reason = "low_snr"
            elif star.roundness < self._min_roundness:
                reason = "elongated"
            elif star.hfd_px > min(18.0, self._stamp_radius * 1.2):
                reason = "extended"
            if reason is None:
                usable.append(star)
            else:
                quality_rejections[reason] = quality_rejections.get(reason, 0) + 1
        usable.sort(key=lambda star: star.snr, reverse=True)
        usable = usable[:20]
        detection["measurement_rejections"] = measurement_rejections
        detection["quality_rejections"] = quality_rejections

        warnings: list[str] = []
        if not candidates:
            warnings.append("no_stars_detected")
        if any(star.saturated for star in measured):
            warnings.append("saturated_stars_rejected")
        if any(star.undersampled for star in usable):
            warnings.append("undersampled_stars")
        if any(
            star.source == "target"
            and star.fwhm_px < 0.35
            and star.concentration >= 0.995
            for star in usable
        ):
            warnings.append("target_may_be_hot_pixel")
        if candidates and not usable:
            warnings.append("no_usable_stars")
        elif len(usable) < 3:
            warnings.append("low_star_count")

        selected: FocusStarMetric | None = None
        if target_x is not None and target_y is not None:
            selected = next((star for star in usable if star.source == "target"), None)
            if selected is None:
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
            "detection": detection,
            "aggregate": aggregate,
            "selected_star": selected.to_dict() if selected is not None else None,
            "stars": [star.to_dict() for star in usable],
            "warnings": warnings,
        }


focus_metric_analyzer = FocusMetricAnalyzer()


__all__ = ["FocusMetricAnalyzer", "FocusStarMetric", "focus_metric_analyzer"]
