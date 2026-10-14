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
    max_saturation_fraction: float = 0.02
    max_step_stops: float = 2.0
    hysteresis_stops: float = 0.12
    settle_frames: int = 2
    fast_step_stops: float = 4.0
    probe_exposure_us: int = 100_000
    # 真实曝光步长；未知时保留旧版 50us 调整死区 / Actual exposure step;
    # retain the legacy 50us adjustment deadband when the step is unknown.
    exposure_step_us: float | None = None


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

    sample_limit = max(1, int(max_samples))
    stride = max(1, int(math.ceil(math.sqrt(values.size / sample_limit))))
    # 奇数步长交替覆盖四个 Bayer 相位，均衡信号抽样；这不是经过色权的 Y。
    # An odd stride alternates all four Bayer phases for balanced signal sampling, not color-weighted Y.
    stride |= 1
    height, width = values.shape[:2]
    # 窄幅或奇数尺寸也必须遵守样本上限 / Keep narrow or odd-sized images within the sample cap too.
    while ((height + stride - 1) // stride) * (
        (width + stride - 1) // stride
    ) > sample_limit:
        stride += 2
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
        self.scene_mode = "starfield"
        self.phase = "searching"
        self._probe_active = False

    def reset(self) -> None:
        """清空收敛历史 / Clear convergence history."""
        self._settle_remaining = 0
        self._filtered_background = None
        self._filtered_highlight = None
        self.phase = "searching"
        self._probe_active = False

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
        previous_background = self._filtered_background
        previous_highlight = self._filtered_highlight
        if previous_background is None or previous_highlight is None:
            filtered_background = stats.background
            filtered_highlight = stats.highlight
        else:
            filtered_background = previous_background + bg_alpha * (
                stats.background - previous_background
            )
            filtered_highlight = previous_highlight + hi_alpha * (
                stats.highlight - previous_highlight
            )
        self._filtered_background = filtered_background
        self._filtered_highlight = filtered_highlight
        return filtered_background, filtered_highlight

    def observe(
        self,
        stats: LuminanceStats,
        *,
        exposure_us: int,
        analogue_gain: float,
        frame_ready: bool | None = None,
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

        if not self.enabled:
            return self._decision(
                exposure_us, analogue_gain, "manual", False, 0.0, stats
            )

        if stats.sample_count <= 0:
            return self._decision(
                exposure_us, analogue_gain, "no_signal", False, 0.0, stats
            )

        # 等待帧可能来自上次曝光，不能污染新曝光下的滤波统计。
        # Settling frames may use old controls; keep them out of the new exposure's filter.
        if frame_ready is False or (frame_ready is None and self._settle_remaining > 0):
            self._settle_remaining = max(0, self._settle_remaining - 1)
            return self._decision(
                exposure_us, analogue_gain, "settling", False, 0.0, stats
            )
        # 大幅场景变化直接计量，避免旧场景的滤波尾巴拖慢双向响应。
        # Meter large scene transitions directly, without an old-scene filter tail.
        if self._filtered_background is not None and (
            stats.saturation_fraction >= 0.20
            or abs(
                math.log2(
                    max(stats.background, 1 / 4096)
                    / max(self._filtered_background, 1 / 4096)
                )
            )
            > 1.0
        ):
            self._filtered_background = None
            self._filtered_highlight = None
        background, highlight = self._filtered_stats(stats)
        product = exposure_us * analogue_gain
        # 用单位曝光的信号判断场景；曝光不足的白天不能误判为夜空。
        # Classify signal per exposure, so underexposed daylight is not mistaken for sky.
        if 0.002 <= stats.background < 0.9:
            scene_signal = stats.background / max(1, product)
            if scene_signal >= 1e-6:
                self.scene_mode = "daylight"
            elif scene_signal <= 2e-7:
                self.scene_mode = "starfield"
        day = self.scene_mode == "daylight"
        target_background = 0.12 if day else self.limits.target_background
        target_highlight = 0.8 if day else self.limits.target_highlight

        # 星空背景应保持暗，星点高分位负责可见性；对数误差对应摄影 EV。
        # Keep sky background dark while the upper percentile drives star visibility.
        background_error = math.log2(target_background / max(background, 1.0 / 4096.0))
        highlight_error = math.log2(target_highlight / max(highlight, 2.0 / 4096.0))
        error_stops = 0.35 * background_error + 0.65 * highlight_error

        # 少量路灯不能压黑星空；允许最多 2% 高光，但继续约束背景亮度。
        # A small lamp must not black out the sky; tolerate 2% clipping while metering background.
        clip_limit = max(0.001, self.limits.max_saturation_fraction)
        if (
            0.001 < stats.saturation_fraction <= clip_limit
            and background < target_background
        ):
            error_stops = background_error
        elif stats.saturation_fraction > clip_limit:
            saturation_ratio = stats.saturation_fraction / clip_limit
            error_stops = min(-0.5, -0.5 * math.log2(max(1.0, saturation_ratio)))

        if abs(error_stops) <= self.limits.hysteresis_stops and not self._probe_active:
            self.phase = "stable"
            return self._decision(
                exposure_us, analogue_gain, "converged", False, error_stops, stats
            )

        searching = abs(error_stops) > 1.5
        step = (
            max(self.limits.max_step_stops, self.limits.fast_step_stops)
            if searching
            else self.limits.max_step_stops
        )
        bounded_stops = max(
            -step,
            min(step, error_stops),
        )
        desired_product = exposure_us * analogue_gain * (2.0**bounded_stops)

        if stats.background >= 0.9 or stats.saturation_fraction >= 0.20:
            # 全白画面没有可靠的线性比值：立即撤增益、缩短快门，再重新测光。
            # Clipped frames cannot give a linear ratio: drop gain/shutter immediately and re-meter.
            next_gain = self.limits.min_gain
            next_exposure = max(
                self.limits.min_exposure_us,
                min(
                    self.limits.probe_exposure_us,
                    self.limits.max_exposure_us,
                    int(round(desired_product / max(analogue_gain, 1.0))),
                ),
            )
            self.phase = "recovering_highlights"
            self._probe_active = True
        elif searching and bounded_stops > 0:
            # 搜索时用短曝光和临时增益加快反馈；信号足够后再恢复低噪声分配。
            # Search with short exposures and temporary gain; restore low-noise allocation afterwards.
            next_exposure = min(
                self.limits.max_exposure_us,
                max(
                    self.limits.min_exposure_us,
                    min(self.limits.probe_exposure_us, int(round(desired_product))),
                    int(round(desired_product / self.limits.max_gain)),
                ),
            )
            next_gain = min(
                self.limits.max_gain,
                max(self.limits.min_gain, desired_product / next_exposure),
            )
            self.phase = "searching_dark"
            self._probe_active = True
        elif searching:
            next_exposure = max(
                self.limits.min_exposure_us, int(round(desired_product / analogue_gain))
            )
            next_gain = max(
                self.limits.min_gain,
                min(self.limits.max_gain, desired_product / next_exposure),
            )
            self.phase = "recovering_highlights"
            self._probe_active = True
        elif bounded_stops < 0 and not self._probe_active:
            # 小幅减光不延长快门；保留原有稳定拍摄的分配。
            # Small darkening corrections never lengthen the shutter.
            next_gain = max(
                self.limits.min_gain,
                min(self.limits.max_gain, desired_product / exposure_us),
            )
            next_exposure = max(
                self.limits.min_exposure_us,
                min(exposure_us, int(round(desired_product / next_gain))),
            )
            self.phase = "fine_adjustment"
        else:
            next_exposure = max(
                self.limits.min_exposure_us,
                min(
                    self.limits.max_exposure_us,
                    int(round(desired_product / self.limits.min_gain)),
                ),
            )
            next_gain = min(
                self.limits.max_gain,
                max(self.limits.min_gain, desired_product / next_exposure),
            )
            self.phase = "fine_adjustment"
            self._probe_active = False

        exposure_step_us = self.limits.exposure_step_us
        if exposure_step_us is not None and exposure_step_us > 0:
            # 比较最近的硬件档位，识别亚毫秒调整并避免重复写回同一曝光行数。
            # Compare nearest hardware steps to detect sub-ms changes without repeatedly writing the same line count.
            # 这里只判定 changed，不改请求值；实际量化和回读仍由驱动负责。
            # This only decides changed, preserving requests; the driver owns actual quantization and readback.
            current_step = round(
                (exposure_us - self.limits.min_exposure_us) / exposure_step_us
            )
            next_step = round(
                (next_exposure - self.limits.min_exposure_us) / exposure_step_us
            )
            exposure_changed = current_step != next_step and abs(
                next_exposure - exposure_us
            ) >= max(1, exposure_us * 0.02)
        else:
            exposure_changed = abs(next_exposure - exposure_us) >= max(
                50, exposure_us * 0.02
            )
        changed = exposure_changed or abs(next_gain - analogue_gain) >= max(
            0.02, analogue_gain * 0.02
        )
        if changed:
            self._settle_remaining = max(0, int(self.limits.settle_frames))
            # 控制改变后重新计量，避免旧暗帧使 AE 持续增亮并过冲。
            # Re-meter after a control change so old dark frames cannot drive overshoot.
            self._filtered_background = None
            self._filtered_highlight = None

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
