"""夜空软件自动曝光控制器 / Night-sky software auto-exposure controller."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(slots=True, frozen=True)
class LuminanceStats:
    """轻量亮度统计，所有亮度归一化到 0..1 / Lightweight normalized luminance stats."""

    background: float
    highlight: float
    saturation_fraction: float
    sample_count: int


@dataclass(slots=True, frozen=True)
class AutoExposureLimits:
    """软件 AE 的硬件与画质边界 / Hardware and image-quality bounds for software AE."""

    min_exposure_us: int = 1_000
    max_exposure_us: int = 2_000_000
    min_gain: float = 1.0
    max_gain: float = 16.0
    target_background: float = 0.035
    target_highlight: float = 0.45
    highlight_percentile: float = 99.8
    max_saturation_fraction: float = 0.001
    max_step_stops: float = 1.0
    hysteresis_stops: float = 0.12
    settle_frames: int = 2


@dataclass(slots=True, frozen=True)
class AutoExposureDecision:
    """一次 AE 观测后的控制决定 / Control decision after one AE observation."""

    exposure_us: int
    analogue_gain: float
    state: str
    changed: bool
    error_stops: float
    background: float
    highlight: float
    saturation_fraction: float


def measure_luminance(
    image: np.ndarray,
    *,
    bit_depth: int = 10,
    black_level: int | float = 0,
    white_level: int | float | None = None,
    highlight_percentile: float = 99.8,
    max_samples: int = 32_768,
) -> LuminanceStats:
    """抽样计算 RAW/灰度亮度统计 / Sample RAW or grayscale luminance statistics."""
    values = np.asarray(image)
    if values.size == 0:
        return LuminanceStats(0.0, 0.0, 0.0, 0)

    if values.ndim >= 3:
        values = np.mean(values[..., :3], axis=-1)

    stride = max(1, int(math.ceil(math.sqrt(values.size / max(1, max_samples)))))
    sampled = np.asarray(values[::stride, ::stride], dtype=np.float32).reshape(-1)
    if sampled.size == 0:
        return LuminanceStats(0.0, 0.0, 0.0, 0)

    if white_level is None:
        if np.issubdtype(values.dtype, np.integer):
            white_level = float((1 << max(1, int(bit_depth))) - 1)
        else:
            observed_max = float(np.max(sampled))
            white_level = 1.0 if observed_max <= 1.0 else observed_max
    black = float(black_level)
    white = max(black + 1.0, float(white_level))
    # 先去除传感器 pedestal 再归一化，否则暗场背景会被固定黑电平误导。
    # Remove the sensor pedestal before normalization so fixed black level cannot bias dark scenes.
    normalized = np.clip((sampled - black) / (white - black), 0.0, 1.0)

    return LuminanceStats(
        background=float(np.percentile(normalized, 50.0)),
        highlight=float(np.percentile(normalized, highlight_percentile)),
        saturation_fraction=float(np.mean(normalized >= 0.985)),
        sample_count=int(normalized.size),
    )


class NightSkyAutoExposure:
    """面向稀疏星点的阻尼软件 AE / Damped software AE for sparse star fields."""

    def __init__(self, limits: AutoExposureLimits):
        self.limits = limits
        self.enabled = True
        self._settle_remaining = 0
        self._filtered_background: float | None = None
        self._filtered_highlight: float | None = None

    def reset(self) -> None:
        """清空收敛历史 / Clear convergence history."""
        self._settle_remaining = 0
        self._filtered_background = None
        self._filtered_highlight = None

    def set_enabled(self, enabled: bool) -> None:
        """切换软件 AE 并在重新启用时重置 / Toggle software AE and reset when enabled."""
        enabled = bool(enabled)
        if enabled and not self.enabled:
            self.reset()
        self.enabled = enabled

    def _filtered_stats(self, stats: LuminanceStats) -> tuple[float, float]:
        # 高光采用更快响应以保护亮星，背景采用较强阻尼防止闪烁。
        # Highlights react faster to protect bright stars; background is more damped.
        bg_alpha = 0.30
        hi_alpha = 0.45
        if self._filtered_background is None:
            self._filtered_background = stats.background
            self._filtered_highlight = stats.highlight
        else:
            self._filtered_background += bg_alpha * (
                stats.background - self._filtered_background
            )
            self._filtered_highlight += hi_alpha * (
                stats.highlight - self._filtered_highlight
            )
        return self._filtered_background, float(self._filtered_highlight or 0.0)

    def observe(
        self,
        stats: LuminanceStats,
        *,
        exposure_us: int,
        analogue_gain: float,
    ) -> AutoExposureDecision:
        """观测一帧并计算下一组曝光参数 / Observe a frame and calculate next exposure settings."""
        exposure_us = int(
            max(
                self.limits.min_exposure_us,
                min(self.limits.max_exposure_us, exposure_us),
            )
        )
        analogue_gain = float(
            max(self.limits.min_gain, min(self.limits.max_gain, analogue_gain))
        )
        background, highlight = self._filtered_stats(stats)

        if not self.enabled:
            return self._decision(
                exposure_us, analogue_gain, "manual", False, 0.0, stats
            )

        if stats.sample_count <= 0:
            return self._decision(
                exposure_us, analogue_gain, "no_signal", False, 0.0, stats
            )

        # 星空背景应保持暗，星点高分位负责可见性；对数误差对应摄影 EV。
        # Keep sky background dark while the upper percentile drives star visibility.
        background_error = math.log2(
            self.limits.target_background / max(background, 1.0 / 4096.0)
        )
        highlight_error = math.log2(
            self.limits.target_highlight / max(highlight, 2.0 / 4096.0)
        )
        error_stops = 0.35 * background_error + 0.65 * highlight_error

        if stats.saturation_fraction > self.limits.max_saturation_fraction:
            saturation_ratio = (
                stats.saturation_fraction / self.limits.max_saturation_fraction
            )
            error_stops = min(-0.5, -0.5 * math.log2(max(1.0, saturation_ratio)))

        if self._settle_remaining > 0:
            self._settle_remaining -= 1
            return self._decision(
                exposure_us, analogue_gain, "settling", False, error_stops, stats
            )

        if abs(error_stops) <= self.limits.hysteresis_stops:
            return self._decision(
                exposure_us, analogue_gain, "converged", False, error_stops, stats
            )

        bounded_stops = max(
            -self.limits.max_step_stops,
            min(self.limits.max_step_stops, error_stops),
        )
        desired_product = exposure_us * analogue_gain * (2.0**bounded_stops)

        if bounded_stops > 0:
            # 增亮优先延长曝光以保留信噪比，达到时长上限后再加模拟增益。
            # Brighten with exposure first for SNR, then use analogue gain at the time limit.
            next_exposure = min(
                self.limits.max_exposure_us,
                max(
                    self.limits.min_exposure_us,
                    int(round(desired_product / analogue_gain)),
                ),
            )
            next_gain = min(
                self.limits.max_gain,
                max(self.limits.min_gain, desired_product / next_exposure),
            )
        else:
            # 变暗时先撤掉增益，再缩短曝光，尽量保留动态范围。
            # Darken by removing gain first, then shorten exposure for dynamic range.
            next_gain = max(
                self.limits.min_gain,
                min(self.limits.max_gain, desired_product / exposure_us),
            )
            next_exposure = max(
                self.limits.min_exposure_us,
                min(
                    self.limits.max_exposure_us, int(round(desired_product / next_gain))
                ),
            )

        changed = abs(next_exposure - exposure_us) >= max(
            50, exposure_us * 0.02
        ) or abs(next_gain - analogue_gain) >= max(0.02, analogue_gain * 0.02)
        if changed:
            self._settle_remaining = max(0, int(self.limits.settle_frames))

        at_dark_limit = (
            next_exposure >= self.limits.max_exposure_us
            and next_gain >= self.limits.max_gain * 0.999
            and error_stops > self.limits.hysteresis_stops
        )
        at_bright_limit = (
            next_exposure <= self.limits.min_exposure_us
            and next_gain <= self.limits.min_gain * 1.001
            and error_stops < -self.limits.hysteresis_stops
        )
        state = (
            "limited_dark"
            if at_dark_limit
            else (
                "limited_bright"
                if at_bright_limit
                else "adjusting" if changed else "converged"
            )
        )
        return self._decision(
            next_exposure, next_gain, state, changed, error_stops, stats
        )

    @staticmethod
    def _decision(
        exposure_us: int,
        analogue_gain: float,
        state: str,
        changed: bool,
        error_stops: float,
        stats: LuminanceStats,
    ) -> AutoExposureDecision:
        return AutoExposureDecision(
            exposure_us=int(exposure_us),
            analogue_gain=round(float(analogue_gain), 3),
            state=state,
            changed=bool(changed),
            error_stops=round(float(error_stops), 3),
            background=round(float(stats.background), 5),
            highlight=round(float(stats.highlight), 5),
            saturation_fraction=round(float(stats.saturation_fraction), 7),
        )
