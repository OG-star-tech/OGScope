"""V4L2 RAW 相机与夜空软件 AE / V4L2 RAW camera with night-sky software AE."""

from __future__ import annotations

import logging
import math
import re
import subprocess
import time
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from ogscope.camera_optics import IMX327_16MM_F14_OPTICS
from ogscope.domain.camera.ae_diagnostics import (
    AutoExposureTraceLimits,
    AutoExposureTraceRecorder,
)
from ogscope.domain.camera.auto_exposure import (
    AutoExposureLimits,
    NightSkyAutoExposure,
    measure_luminance,
)
from ogscope.domain.camera.driver import CameraCapabilities

logger = logging.getLogger(__name__)

# 软件自动曝光引擎允许的最长曝光时间上限（策略性，不是硬件限制 - 真实硬件
# 上限由 vertical_blanking 等控件动态推导，见 _resolve_line_duration）。
# 2026-09-20 在真实 Zero2W (192.168.0.41) 上验证 1s-3s 手动曝光（控件写入/
# 回读与实际抓帧均正常）后，产品决策从 1s 放宽到 3s - 见
# docs/development/v4l2-zero2w-board-validation.md。/
# Ceiling on how long the software auto-exposure engine may drive exposure
# (a policy limit, not a hardware one - the real hardware ceiling is derived
# dynamically from vertical_blanking and friends, see
# _resolve_line_duration). Raised from 1s to 3s as a product decision on
# 2026-09-20 after validating manual 1s-3s exposure (control write/readback
# and real capture, both clean) on a real Zero2W (192.168.0.41) - see
# docs/development/v4l2-zero2w-board-validation.md.
AUTO_EXPOSURE_MAX_CEILING_US = 3_000_000

# 这颗传感器（v4l2-ctl --list-ctrls）根本没有暴露任何黑电平控件，
# _resolve_signal_levels() 的自动探测必然失败，退回的旧默认值是 0 —— 意味着
# 完全没有黑电平校正，gamma 曲线从原始编码 0 开始放大，而不是从传感器真实的
# 暗场地板开始。用遮住镜头（零入射光）在真实 Zero2W 上实测：10ms-3s 曝光下
# 均值稳定在 240.5-244.1（12 位满量程 4095），暗电流增长速率仅约
# 1.2 counts/sec（可忽略，不需要按曝光时间动态调整）。这里把退回默认值从
# 0 改成这个实测值按位深换算的比例，而不是继续用明显错误的 0 —— 见
# docs/development/v4l2-zero2w-board-validation.md 的暗场标定记录。
# This sensor (per `v4l2-ctl --list-ctrls`) exposes no black-level control at
# all, so _resolve_signal_levels()'s auto-detect always fails and used to
# fall back to 0 - meaning zero black-level correction was ever applied, and
# the gamma curve amplified the raw signal from code 0 instead of the
# sensor's real dark floor. Measured on real Zero2W hardware with the lens
# covered (zero incident light): mean raw value held steady at 240.5-244.1
# (of a 4095 12-bit full range) across 10ms-3s exposure, with a negligible
# ~1.2 counts/sec dark-current rate (no need for exposure-dependent
# scaling). This replaces the old, provably-wrong 0 fallback with that
# measured value, scaled proportionally by bit depth - see
# docs/development/v4l2-zero2w-board-validation.md for the calibration.
FALLBACK_BLACK_LEVEL_FRACTION_OF_FULL_RANGE = 240.5 / 4095.0

# gamma 查找表的过采样倍数：时域降噪在线性 RAW 域完成，平均后的 RAW 带亚整数
# 精度，查表前四舍五入回整数会把这部分精度量化掉。16 倍过采样把量化步长压到
# 1/16 个 RAW 编码值，远低于实测的最小输出噪声（10ms 曝光约 0.17 个编码值），
# 代价只有 12 位下 64KB 的表。
# Oversampling factor for the gamma LUT: temporal NR runs in the linear RAW
# domain, so averaged RAW values carry sub-integer precision that rounding to
# integers before the lookup would quantize away. 16x puts the quantization
# step at 1/16 of a RAW code, well under the smallest measured output noise
# (~0.17 codes at 10ms), for a 64KB table at 12-bit.
GAMMA_LUT_OVERSAMPLE = 16


@dataclass(slots=True, frozen=True)
class V4L2ControlRange:
    """V4L2 整数控件范围 / V4L2 integer control range."""

    minimum: int
    maximum: int
    step: int
    default: int
    value: int


class V4L2RawCamera:
    """直接 RAW 抓帧并在应用层闭环曝光 / Direct RAW capture with application AE."""

    _CONTROL_LINE_RE = re.compile(
        r"^\s*([a-zA-Z0-9_]+)\s+0x[0-9a-fA-F]+\s+\([^)]*\)\s*:\s*(.*)$"
    )
    _VALUE_RE = re.compile(r"\b(min|max|step|default|value)=(-?\d+)")

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.driver_name = "v4l2-imx327-software-ae"
        self.backend_name = "opencv/v4l2-raw"
        self.output_pixel_format = "RGB888"
        self.device = str(config.get("device", "/dev/video0"))
        self.sensor_subdev = str(config.get("v4l2_sensor_subdev", "/dev/v4l-subdev1"))
        self.media_device = str(config.get("v4l2_media_device", "/dev/media0"))
        self.configure_media_pipeline = bool(
            config.get("v4l2_configure_media_pipeline", True)
        )
        self.sensor_entity = str(config.get("v4l2_sensor_entity", "imx327 10-001a"))
        self.receiver_entity = str(config.get("v4l2_receiver_entity", "unicam"))
        self.sensor_pad = int(config.get("v4l2_sensor_pad", 0))
        self.receiver_sink_pad = int(config.get("v4l2_receiver_sink_pad", 0))
        self.receiver_source_pad = int(config.get("v4l2_receiver_source_pad", 1))
        self.media_bus_format = str(
            config.get("v4l2_media_bus_format", "SRGGB10_1X10")
        ).upper()
        self.pixel_format = str(config.get("v4l2_pixel_format", "RG10")).upper()
        self.bit_depth = int(config.get("v4l2_bit_depth", 10))
        self._black_level_override = int(config.get("v4l2_black_level", -1))
        self._white_level_override = int(config.get("v4l2_white_level", 0))
        self.black_level = 0
        self.white_level = (1 << self.bit_depth) - 1
        self._signal_level_sources = {
            "black_level": "fallback",
            "white_level": "bit_depth",
        }
        requested_bayer = str(config.get("v4l2_bayer_pattern", "RGGB")).upper()
        self.bayer_pattern = (
            requested_bayer
            if requested_bayer in {"RGGB", "BGGR", "GRBG", "GBRG"}
            else "RGGB"
        )
        self.active_width = int(config.get("v4l2_active_width", 1920))
        self.active_height = int(config.get("v4l2_active_height", 1080))
        self.width = max(160, int(config.get("width", 1280)))
        self.height = max(120, int(config.get("height", 720)))
        self.output_width = self.width
        self.output_height = self.height
        self.capture_width = self.active_width
        self.capture_height = self.active_height
        self.fps = max(1, int(config.get("fps", 5)))
        self.rotation = int(config.get("rotation", 0))
        self.flip_horizontal = bool(config.get("flip_horizontal", False))
        self.flip_vertical = bool(config.get("flip_vertical", False))
        requested_sampling = str(config.get("sampling_mode", "native")).lower()
        self.sampling_mode = (
            requested_sampling
            if requested_sampling in {"native", "supersample", "crop"}
            else "native"
        )
        self.color_mode = str(config.get("color_mode", "color"))
        requested_white_balance = str(config.get("white_balance_mode", "night"))
        # RAW 路径没有 ISP AWB；把产品默认 auto 明确映射为稳定的夜空白平衡。
        # The RAW path has no ISP AWB; map the product default auto to stable night WB.
        self.white_balance_mode = (
            "night" if requested_white_balance == "auto" else requested_white_balance
        )
        self.white_balance_gain_r = float(config.get("white_balance_gain_r", 1.0))
        self.white_balance_gain_b = float(config.get("white_balance_gain_b", 1.0))
        self.night_mode = bool(config.get("night_mode", True))
        self.noise_reduction_mode = "off"
        self.ae_flicker_mode = "off"

        self.exposure_us = int(config.get("exposure_us", 10_000))
        self.analogue_gain = float(config.get("analogue_gain", 1.0))
        self.requested_exposure_us = self.exposure_us
        self.requested_analogue_gain = self.analogue_gain
        self.actual_exposure_us: int | None = None
        self.actual_analogue_gain: float | None = None
        self._control_readback_verified = False
        self._control_readback_error: str | None = "not_read_yet"
        self.digital_gain = 1.0
        self.auto_exposure = bool(config.get("auto_exposure", True))
        self.auto_exposure_max_us = max(
            10_000,
            min(
                AUTO_EXPOSURE_MAX_CEILING_US,
                int(config.get("auto_exposure_max_us", AUTO_EXPOSURE_MAX_CEILING_US)),
            ),
        )
        self._hardware_max_exposure_us = self.auto_exposure_max_us
        self.gain_db_per_step = float(config.get("v4l2_gain_db_per_step", 0.3))
        self.auto_gain_max = float(config.get("v4l2_auto_gain_max", 16.0))
        self._line_duration_override_us = float(
            config.get("v4l2_line_duration_us", 0.0)
        )
        self._line_duration_us = self._line_duration_override_us or 8.0
        self._line_duration_source = (
            "config" if self._line_duration_override_us > 0 else "fallback"
        )

        self.contrast = float(config.get("contrast", 1.0))
        self.brightness = float(config.get("brightness", 0.0))
        self.saturation = float(config.get("saturation", 1.0))
        self.sharpness = float(config.get("sharpness", 1.0))
        # RAW 路径没有 ISP 色调曲线；线性拉伸后的画面对比度明显低于
        # picamera2/libcamera 的输出，同一 sigma 阈值下提星命中率也明显更低
        # （实测：同场景、相同曝光下 picamera2 检出 7 颗，V4L2 仅 1 颗，见
        # docs/development/v4l2-zero2w-board-validation.md）。这里补一条与
        # ISP 大致等效的 gamma 校正，让下游提星阈值在两条后端上可复用。
        # The RAW path has no ISP tone curve; the linear stretch produces
        # markedly lower contrast than picamera2/libcamera's output, and
        # measurably fewer centroid detections at the same sigma threshold
        # (same scene, same exposure: picamera2 found 7, V4L2 found 1 - see
        # docs/development/v4l2-zero2w-board-validation.md). This adds a
        # gamma correction roughly matching the ISP's tone curve so the
        # downstream centroid threshold is reusable across both backends.
        self.gamma = max(1.0, float(config.get("v4l2_gamma", 2.2)))
        # 建在 initialize() 里、_resolve_signal_levels() 之后（需要真实黑/白
        # 电平）/ Built in initialize(), after _resolve_signal_levels() (needs
        # the resolved black/white levels).
        self._gamma_lut: np.ndarray | None = None
        # 曾在此处加过一级 CLAHE 局部对比度增强，已撤销：在真实 Zero2W 上实测
        # （不同 clip_limit 1.0-3.0），即便很保守的设置也会把 patch_noise_std
        # 从 gamma-only 的 0.58 推到 1.2+（picamera2 是 0.68），提星命中数始终
        # 是 0-1（picamera2 同场景 6-7 颗），说明 CLAHE 只是在放大暗/平坦区域
        # 的传感器噪声、没有真正提升星点可探测性。等效对比度需求应该靠给
        # V4L2 后端单独调 solver_centroid_sigma 解决，而不是让画面在视觉上
        # 冒充 picamera2 的输出。见
        # docs/development/v4l2-zero2w-board-validation.md 的复测记录。
        # A CLAHE local-contrast stage was added here and reverted: measured
        # on real Zero2W hardware across clip_limit 1.0-3.0, even
        # conservative settings pushed patch_noise_std from gamma-only's 0.58
        # up to 1.2+ (picamera2's own is 0.68), while centroid counts stayed
        # at 0-1 (picamera2 finds 6-7 on the same scene) - CLAHE was just
        # amplifying sensor noise in dark/flat regions, not improving real
        # star detectability. Matching detection sensitivity should be solved
        # with a V4L2-specific solver_centroid_sigma, not by cosmetically
        # reshaping the image to imitate picamera2's output. See
        # docs/development/v4l2-zero2w-board-validation.md for the retest.
        #
        # 真正的根因随后在真实硬件上用时域方法测出来了：对着完全静止的场景连拍
        # 10 帧，逐像素算跨帧标准差（场景没变，帧间差异就是纯噪声），picamera2
        # 是 0.55，V4L2（仅 gamma）是 3.55 —— 差 6.5 倍，SNR 差了近 10 倍。根因是
        # V4L2 这条路径完全没有降噪（noise_reduction_mode 硬编码 "off"，见下），
        # 而 picamera2 的 ISP 默认做真实降噪。这解释了之前对比度不够的很大一部分
        # 原因：gamma/CLAHE 都只是在给同一份带噪声的信号重新分布亮度，没有真正去
        # 噪声。这里加一级时域指数滑动平均（EMA）：产品场景是静态/跟踪的星空，帧
        # 间场景基本不变，时域累积能在不损失空间分辨率的前提下把随机噪声降下去
        # （空间滤波比如高斯/双边会牺牲真实细节）。曝光/增益一变就清空累积器，
        # 避免在 AE 调整/收敛过程中把不同亮度的帧混在一起。
        # The real root cause was found afterward via a proper hardware
        # methodology: 10 frames of a completely static scene, per-pixel
        # temporal std (scene didn't change, so any frame-to-frame variation
        # IS noise) - picamera2: 0.55, V4L2 (gamma only): 3.55, a 6.5x gap,
        # ~10x worse SNR. Root cause: this path applies zero noise reduction
        # (noise_reduction_mode hardcoded "off", see below) while picamera2's
        # ISP applies real denoising by default. This explains much of the
        # earlier contrast shortfall - gamma/CLAHE were both just redistributing
        # brightness on the same noisy signal, never actually removing noise.
        # Adds a temporal exponential-moving-average (EMA) stage: the product's
        # real scenes are static/tracked astrophotography, so temporal
        # accumulation reduces random noise without sacrificing spatial
        # resolution (unlike spatial filtering, e.g. Gaussian/bilateral, which
        # trades away real detail). Resets on any exposure/gain change to avoid
        # blending frames of different brightness during AE adjustment/settling.
        self.temporal_nr_alpha = max(
            0.01, min(1.0, float(config.get("v4l2_temporal_nr_alpha", 0.2)))
        )
        # EMA 的时间常数按"秒"而不是按"帧"来定：短曝光下每秒能拿到很多帧，
        # 多平均几十帧的墙钟代价可以忽略，所以可以用小得多的 alpha 换大得多
        # 的降噪；长曝光下每帧就要好几秒，平均更多帧的代价是实打实的延迟，
        # 所以退回 temporal_nr_alpha 这个上限（= 最少平均帧数 1/alpha）。
        # The EMA time constant is defined in SECONDS rather than frames:
        # at short exposures many frames arrive per second, so averaging
        # tens of them costs negligible wall-clock time and buys a much
        # smaller alpha (much stronger denoise); at long exposures each
        # frame costs seconds, so averaging more of them is real latency and
        # it falls back to the temporal_nr_alpha bound (= a floor of 1/alpha
        # averaged frames).
        self.temporal_nr_seconds = max(
            0.0, float(config.get("v4l2_temporal_nr_seconds", 2.0))
        )
        self.temporal_nr_max_frames = max(
            1, int(config.get("v4l2_temporal_nr_max_frames", 50))
        )
        self._nr_accumulator: np.ndarray | None = None
        # 累积器是否持有有效历史。曝光/增益一变要丢弃历史，但不能把数组
        # 本身丢掉：AE 收敛期间每帧都可能触发一次，反复重新分配整幅
        # float32 会让 RSS 一路涨上去（实测开着 AE 抓 40 帧涨了 38MB）。
        # 置为无效即可，下一帧原地覆盖。
        # Whether the accumulator holds valid history. An exposure/gain
        # change must discard the history but must NOT drop the array:
        # during AE convergence that can fire every frame, and
        # reallocating a full-frame float32 each time walks RSS upward
        # (measured: +38MB over 40 frames with AE enabled). Marking it
        # invalid lets the next frame overwrite it in place.
        self._nr_accumulator_valid = False
        # 重置之后，仍要拒绝把帧当作新种子，直到经过至少一次完整曝光时长
        # 为止：否则第一帧可能是曝光起始时间早于重置点的旧帧（本身就带
        # 拖线），被当成"全新种子"后，之后真正干净的帧还要跟这帧混合几帧
        # 才收敛，肉眼看到的就是新旧画面之间的渐变/叠影。0 表示当前没有
        # 处于这个等待窗口。
        # / After a reset, frames must still not be trusted as the new seed
        # until at least one full exposure duration has elapsed: otherwise
        # the very first frame can be one whose exposure started before the
        # reset point (itself already trailed), and once accepted as the
        # "fresh seed", genuinely clean frames keep blending against it for
        # several more frames before converging - visible as a fade/ghost
        # between the old and new scene. 0 means no such window is active.
        self._nr_fresh_epoch_deadline_mono = 0.0
        # 整幅 float32 的复用暂存：时域降噪先用完、_debayer 再用，两者
        # 生命周期不重叠，所以共用一块即可（各自单独分配会白白多占 3.7MB）
        # / One reused full-frame float32 scratch: temporal NR finishes
        # with it before _debayer needs one, so their lifetimes never
        # overlap and separate buffers would just waste 3.7MB.
        self._frame_scratch: np.ndarray | None = None
        self._lut_index_buffer: np.ndarray | None = None
        # 色调查找表及其参数键 / Tone LUT and the parameter key it was built for.
        self._tone_lut_cache: np.ndarray | None = None
        self._tone_lut_key: tuple | None = None

        self.is_initialized = False
        self.is_capturing = False
        self._capture: Any | None = None
        self._capture_format: dict[str, Any] = {}
        self._media_pipeline: dict[str, Any] = {
            "enabled": self.configure_media_pipeline,
            "state": "not_configured" if self.configure_media_pipeline else "disabled",
            "error": None,
        }
        self._control_ranges: dict[str, V4L2ControlRange] = {}
        self._last_ae: dict[str, Any] = {
            "state": "starting" if self.auto_exposure else "manual"
        }
        self._last_luminance: dict[str, Any] = {}
        self._frame_duration_us = 0
        self._ae = self._create_auto_exposure()
        self._ae.set_enabled(self.auto_exposure)
        self._trace = AutoExposureTraceRecorder(
            enabled=bool(config.get("v4l2_ae_trace_enabled", False)),
            root_dir=str(config.get("v4l2_ae_trace_dir", "./data/camera-ae-traces")),
            limits=AutoExposureTraceLimits(
                max_events=int(config.get("v4l2_ae_trace_max_events", 2_000)),
                raw_sample_interval=int(
                    config.get("v4l2_ae_trace_raw_sample_interval", 10)
                ),
                max_raw_samples=int(config.get("v4l2_ae_trace_max_raw_samples", 100)),
                raw_max_side=int(config.get("v4l2_ae_trace_raw_max_side", 320)),
            ),
        )

    def _create_auto_exposure(self) -> NightSkyAutoExposure:
        effective_max_gain = max(1.0, float(self.auto_gain_max))
        gain_control = self._control_ranges.get("analogue_gain")
        if gain_control is not None:
            effective_max_gain = min(
                effective_max_gain,
                self._control_to_gain(gain_control.maximum),
            )
        return NightSkyAutoExposure(
            AutoExposureLimits(
                min_exposure_us=1_000,
                max_exposure_us=max(
                    10_000,
                    min(
                        int(self.auto_exposure_max_us),
                        int(self._hardware_max_exposure_us),
                    ),
                ),
                min_gain=1.0,
                max_gain=effective_max_gain,
                target_background=float(
                    self.config.get("v4l2_ae_target_background", 0.035)
                ),
                target_highlight=float(
                    self.config.get("v4l2_ae_target_highlight", 0.45)
                ),
                highlight_percentile=float(
                    self.config.get("v4l2_ae_highlight_percentile", 99.8)
                ),
            )
        )

    def _run_v4l2(
        self, *args: str, timeout: float = 2.0
    ) -> subprocess.CompletedProcess:
        """运行无 shell 的 V4L2 控制命令 / Run a shell-free V4L2 control command."""
        return subprocess.run(
            ["v4l2-ctl", "-d", self.sensor_subdev, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def _configure_media_pipeline(self) -> bool:
        """按板级实体配置 RAW 媒体链路 / Configure the board-specific RAW media graph."""
        if not self.configure_media_pipeline:
            self._media_pipeline = {
                "enabled": False,
                "state": "disabled",
                "error": None,
            }
            return True

        configured_targets = (
            (self.sensor_entity, self.sensor_pad),
            (self.receiver_entity, self.receiver_sink_pad),
            (self.receiver_entity, self.receiver_source_pad),
        )
        # 有些 Unicam 拓扑只暴露传感器 subdev；负 pad 让部署配置跳过不存在的接收器 pad。
        # Some Unicam graphs expose only the sensor subdev; negative pads skip absent receiver pads.
        targets = tuple((entity, pad) for entity, pad in configured_targets if pad >= 0)
        for entity, pad in targets:
            target = (
                f'"{entity}":{pad}[fmt:{self.media_bus_format}/'
                f"{self.active_width}x{self.active_height}]"
            )
            try:
                result = subprocess.run(
                    [
                        "media-ctl",
                        "-d",
                        self.media_device,
                        "--set-v4l2",
                        target,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=2.0,
                    check=False,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                self._media_pipeline = {
                    "enabled": True,
                    "state": "error",
                    "error": str(exc),
                }
                logger.error(
                    "配置 V4L2 媒体链路失败 / Failed to configure media graph: %s",
                    exc,
                )
                return False
            if result.returncode != 0:
                error = result.stderr.strip() or f"media-ctl exit {result.returncode}"
                self._media_pipeline = {
                    "enabled": True,
                    "state": "error",
                    "error": error,
                }
                logger.error(
                    "配置 V4L2 实体失败 / Failed to configure V4L2 entity %s:%s: %s",
                    entity,
                    pad,
                    error,
                )
                return False
        self._media_pipeline = {"enabled": True, "state": "configured", "error": None}
        return True

    def _discover_control_ranges(self) -> bool:
        """读取实际控件范围，拒绝静默假自动 / Read actual controls and reject fake AE."""
        try:
            result = self._run_v4l2("--list-ctrls")
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.error("V4L2 控制工具不可用 / v4l2-ctl unavailable: %s", exc)
            return False
        if result.returncode != 0:
            logger.error(
                "读取 V4L2 控件失败 / Failed to list V4L2 controls: %s", result.stderr
            )
            return False

        ranges: dict[str, V4L2ControlRange] = {}
        for line in result.stdout.splitlines():
            match = self._CONTROL_LINE_RE.match(line)
            if not match:
                continue
            fields = {
                key: int(value) for key, value in self._VALUE_RE.findall(match.group(2))
            }
            if "min" not in fields or "max" not in fields:
                continue
            ranges[match.group(1)] = V4L2ControlRange(
                minimum=fields["min"],
                maximum=fields["max"],
                step=max(1, fields.get("step", 1)),
                default=fields.get("default", fields["min"]),
                value=fields.get("value", fields.get("default", fields["min"])),
            )
        self._control_ranges = ranges
        required = {"exposure", "analogue_gain"}
        missing = sorted(required - ranges.keys())
        if missing:
            logger.error(
                "V4L2 缺少软件 AE 必需控件 / Missing controls required by software AE: %s",
                ", ".join(missing),
            )
            return False
        return True

    def _read_controls(self, *names: str) -> dict[str, int]:
        """一次读取多个整数控件 / Read multiple integer controls in one call."""
        if not names:
            return {}
        try:
            result = self._run_v4l2(f"--get-ctrl={','.join(names)}")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return {}
        if result.returncode != 0:
            return {}
        values: dict[str, int] = {}
        for line in result.stdout.splitlines():
            if ":" not in line:
                continue
            name, value = line.split(":", 1)
            try:
                values[name.strip()] = int(value.strip())
            except ValueError:
                continue
        return values

    def _read_control(self, name: str) -> int | None:
        """读取单个整数控件 / Read one integer control."""
        return self._read_controls(name).get(name)

    def _set_control(self, name: str, value: int) -> bool:
        """写入单个整数控件 / Write one integer control."""
        try:
            result = self._run_v4l2(f"--set-ctrl={name}={int(value)}")
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.error("设置 V4L2 控件异常 / V4L2 control write failed: %s", exc)
            return False
        if result.returncode != 0:
            logger.warning(
                "设置 V4L2 控件失败 / Failed to set V4L2 control %s=%s: %s",
                name,
                value,
                result.stderr.strip(),
            )
            return False
        return True

    def _resolve_line_duration(self) -> None:
        """优先从 pixel_rate 与 hblank 推导行周期 / Derive line time from pixel rate and hblank."""
        if self._line_duration_override_us > 0:
            self._line_duration_us = self._line_duration_override_us
            self._line_duration_source = "config"
        else:
            pixel_rate = self._read_control("pixel_rate")
            hblank = self._read_control("horizontal_blanking")
            if pixel_rate and pixel_rate > 0 and hblank is not None:
                self._line_duration_us = (
                    (self.active_width + hblank) * 1_000_000.0 / pixel_rate
                )
                self._line_duration_source = "sensor_controls"
            else:
                self._line_duration_us = 8.0
                self._line_duration_source = "fallback"
        vblank = self._control_ranges.get("vertical_blanking")
        exposure = self._control_ranges.get("exposure")
        if vblank is not None:
            max_lines = self.active_height + vblank.maximum - 4
        elif exposure is not None:
            max_lines = exposure.maximum
        else:
            max_lines = max(1, int(self.auto_exposure_max_us / self._line_duration_us))
        self._hardware_max_exposure_us = max(
            10_000, int(max_lines * self._line_duration_us)
        )

    def _resolve_signal_levels(self) -> None:
        """解析 RAW 黑白电平并保留来源 / Resolve RAW black/white levels with provenance."""
        max_code = (1 << max(1, self.bit_depth)) - 1
        if self._black_level_override >= 0:
            black = self._black_level_override
            black_source = "config"
        else:
            detected_black = self._read_control("black_level")
            if detected_black is not None:
                black = detected_black
                black_source = "sensor_control"
            else:
                black = round(FALLBACK_BLACK_LEVEL_FRACTION_OF_FULL_RANGE * max_code)
                black_source = "fallback_measured_dark_frame"

        if self._white_level_override > 0:
            white = self._white_level_override
            white_source = "config"
        else:
            detected_white = self._read_control("white_level")
            white = detected_white if detected_white is not None else max_code
            white_source = (
                "sensor_control" if detected_white is not None else "bit_depth"
            )

        self.black_level = max(0, min(max_code - 1, int(black)))
        self.white_level = max(self.black_level + 1, min(max_code, int(white)))
        self._signal_level_sources = {
            "black_level": black_source,
            "white_level": white_source,
        }

    @staticmethod
    def _clamp_to_control(value: int, control: V4L2ControlRange) -> int:
        bounded = max(control.minimum, min(control.maximum, int(value)))
        return (
            control.minimum
            + ((bounded - control.minimum) // control.step) * control.step
        )

    def _gain_to_control(self, gain: float) -> int:
        control = self._control_ranges["analogue_gain"]
        gain = max(1.0, float(gain))
        gain_db = 20.0 * math.log10(gain)
        raw = control.minimum + int(round(gain_db / self.gain_db_per_step))
        return self._clamp_to_control(raw, control)

    def _control_to_gain(self, raw: int) -> float:
        control = self._control_ranges["analogue_gain"]
        gain_db = max(0, raw - control.minimum) * self.gain_db_per_step
        return float(10.0 ** (gain_db / 20.0))

    def _apply_exposure_gain(self, exposure_us: int, gain: float) -> bool:
        """按 vblank、曝光、增益顺序原子化更新 / Update vblank, exposure, then gain."""
        exposure_control = self._control_ranges["exposure"]
        requested_lines = max(1, int(round(exposure_us / self._line_duration_us)))

        vblank_control = self._control_ranges.get("vertical_blanking")
        if vblank_control is not None:
            required_vblank = requested_lines - self.active_height + 4
            vblank = self._clamp_to_control(required_vblank, vblank_control)
            if not self._set_control("vertical_blanking", vblank):
                return False
            max_lines = self.active_height + vblank - 4
            requested_lines = min(requested_lines, max_lines)
            # 传感器驱动会随 vblank 动态提高 exposure.max，不能使用调整前缓存的上限。
            # Sensor drivers raise exposure.max with vblank; do not reuse the stale pre-vblank maximum.
            dynamic_exposure_control = V4L2ControlRange(
                exposure_control.minimum,
                max(exposure_control.minimum, max_lines),
                exposure_control.step,
                exposure_control.default,
                exposure_control.value,
            )
        else:
            dynamic_exposure_control = exposure_control

        exposure_lines = self._clamp_to_control(
            requested_lines, dynamic_exposure_control
        )
        gain_control = self._gain_to_control(gain)
        self.requested_exposure_us = int(exposure_us)
        self.requested_analogue_gain = float(gain)
        if not self._set_control("exposure", exposure_lines):
            return False
        if not self._set_control("analogue_gain", gain_control):
            return False

        estimated_exposure_us = max(
            1, int(round(exposure_lines * self._line_duration_us))
        )
        estimated_gain = round(self._control_to_gain(gain_control), 3)
        readback_names = ["exposure", "analogue_gain"]
        if vblank_control is not None:
            readback_names.append("vertical_blanking")
        readback = self._read_controls(*readback_names)
        if "exposure" in readback and "analogue_gain" in readback:
            self.actual_exposure_us = max(
                1, int(round(readback["exposure"] * self._line_duration_us))
            )
            self.actual_analogue_gain = round(
                self._control_to_gain(readback["analogue_gain"]), 3
            )
            self.exposure_us = self.actual_exposure_us
            self.analogue_gain = self.actual_analogue_gain
            self._control_readback_verified = True
            self._control_readback_error = None
        else:
            self.exposure_us = estimated_exposure_us
            self.analogue_gain = estimated_gain
            self.actual_exposure_us = None
            self.actual_analogue_gain = None
            self._control_readback_verified = False
            missing = sorted({"exposure", "analogue_gain"} - readback.keys())
            self._control_readback_error = "missing:" + ",".join(missing)
        frame_lines = self.active_height
        if vblank_control is not None:
            frame_lines += readback.get("vertical_blanking", vblank)
        self._frame_duration_us = max(
            self.exposure_us, int(round(frame_lines * self._line_duration_us))
        )
        # 曝光/增益真的变了，累积的是不同亮度的帧，作废历史避免下一帧被
        # 拖回旧亮度；保留数组本身，下一帧原地覆盖 / Exposure/gain actually
        # changed, so the accumulated history is at a different brightness -
        # invalidate it so the next frame isn't blended back toward the old
        # level, but keep the array itself for in-place reuse.
        self._nr_accumulator_valid = False
        return True

    def _create_capture(self) -> Any | None:
        """打开 V4L2 RAW 视频节点 / Open the V4L2 RAW video node."""
        import cv2

        capture = cv2.VideoCapture(self.device, cv2.CAP_V4L2)
        if not capture.isOpened():
            logger.error(
                "无法打开 V4L2 相机 / Cannot open V4L2 camera: %s", self.device
            )
            capture.release()
            return None
        try:
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.active_width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.active_height)
            fourcc = sum(
                ord(character) << (8 * index)
                for index, character in enumerate(self.pixel_format)
            )
            capture.set(cv2.CAP_PROP_FOURCC, fourcc)
            capture.set(cv2.CAP_PROP_CONVERT_RGB, 0)
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            read_timeout = getattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC", None)
            if read_timeout is not None:
                capture.set(
                    read_timeout,
                    max(
                        500,
                        int(float(self.config.get("capture_timeout_sec", 8.0)) * 1000),
                    ),
                )

            actual_width = int(round(capture.get(cv2.CAP_PROP_FRAME_WIDTH)))
            actual_height = int(round(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
            actual_fourcc_value = int(round(capture.get(cv2.CAP_PROP_FOURCC)))
            actual_fourcc = "".join(
                chr((actual_fourcc_value >> (8 * index)) & 0xFF) for index in range(4)
            ).rstrip("\x00 ")
            self._capture_format = {
                "requested_fourcc": self.pixel_format,
                "actual_fourcc": actual_fourcc or "unknown",
                "actual_width": actual_width,
                "actual_height": actual_height,
            }

            # OpenCV/V4L2 可能接受 set() 却静默退回 YUV；RAW 解包前必须拒绝这种状态。
            # OpenCV/V4L2 may accept set() while silently falling back to YUV; reject it before RAW unpacking.
            format_mismatch = actual_fourcc != self.pixel_format
            size_mismatch = (actual_width, actual_height) != (
                self.active_width,
                self.active_height,
            )
            if not format_mismatch and not size_mismatch:
                return capture
            logger.error(
                "V4L2 RAW 协商结果不匹配 / Negotiated V4L2 RAW format mismatch: %s",
                self._capture_format,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "V4L2 RAW 节点配置失败 / Failed to configure V4L2 RAW node: %s",
                exc,
            )
        capture.release()
        return None

    def initialize(self) -> bool:
        """初始化 RAW 抓帧和软件 AE / Initialize RAW capture and software AE."""
        try:
            if not self._configure_media_pipeline():
                return False
            if not self._discover_control_ranges():
                return False
            self._resolve_line_duration()
            self._resolve_signal_levels()
            self._gamma_lut = self._build_gamma_lut()
            enabled = self.auto_exposure
            self._ae = self._create_auto_exposure()
            self._ae.set_enabled(enabled)
            if not self._apply_exposure_gain(self.exposure_us, self.analogue_gain):
                return False
            self._capture = self._create_capture()
            if self._capture is None:
                return False
            self._trace.start(
                {
                    "driver": self.driver_name,
                    "device": self.device,
                    "sensor_subdev": self.sensor_subdev,
                    "media_device": self.media_device,
                    "media_pipeline": self._media_pipeline,
                    "pixel_format": self.pixel_format,
                    "bit_depth": self.bit_depth,
                    "signal_levels": {
                        "black_level": self.black_level,
                        "white_level": self.white_level,
                        "sources": self._signal_level_sources,
                    },
                    "auto_exposure_limits": asdict(self._ae.limits),
                    "control_ranges": {
                        name: asdict(control)
                        for name, control in self._control_ranges.items()
                    },
                }
            )
            self.is_initialized = True
            logger.info(
                "V4L2 软件 AE 相机初始化成功 / V4L2 software-AE camera initialized: "
                "line=%.3fus source=%s",
                self._line_duration_us,
                self._line_duration_source,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("V4L2 相机初始化失败 / V4L2 initialization failed: %s", exc)
            self.close()
            return False

    def start_capture(self) -> bool:
        """开始抓帧 / Start capture."""
        if not self.is_initialized:
            return False
        if self._capture is None:
            self._capture = self._create_capture()
        if self._capture is None:
            return False
        self.is_capturing = True
        # 每次开始抓帧都是新的一段序列，之前累积的帧可能是很久以前的场景
        # / Each capture start is a fresh sequence - a stale accumulator from
        # a previous run could hold a since-changed scene.
        self._nr_accumulator_valid = False
        return True

    def begin_fresh_capture_epoch(self) -> None:
        """新分析会话/移动结算起点：失效累积器并等过一次完整曝光 / New
        analysis-session or settle epoch: invalidate the accumulator and
        wait out one full exposure before trusting a frame as the new seed.

        预览通常持续采集；仅仅失效累积器不够——调用这个方法的时刻，传感器
        可能已经在曝光一帧，其曝光起始时间早于调用点（甚至早于底座真正停
        稳），这一帧本身可能已经带有拖线。如果直接把它当成"全新种子"，之
        后真正干净的帧还要跟它混合几帧才收敛，肉眼看到的就是新旧画面之间
        的渐变/叠影。所以在至少一次完整曝光时长内，持续用当前帧原地覆盖
        （不建立种子、不参与混合），只有曝光起始时间确定晚于调用点的帧才
        会被接受为新种子；不重新分配数组，保留此前修复的 RSS 收益。
        Preview capture usually keeps running. Just invalidating the
        accumulator is not enough: at the moment this is called, the sensor
        may already be mid-exposure on a frame whose exposure started
        before this call (even before the mount actually stopped), so that
        frame can itself already be trailed. Accepting it outright as the
        "fresh seed" means genuinely clean frames keep blending against it
        for several more frames before converging - visible as a fade/ghost
        between the old and new scene. So for at least one full exposure
        duration, every frame keeps overwriting the accumulator in place
        (no seed established, no blending) - only a frame whose exposure is
        guaranteed to have started after this call becomes the new seed.
        Arrays are not reallocated, preserving the earlier RSS fix.
        """
        self._nr_accumulator_valid = False
        frame_duration_s = max(
            1e-3, float(self._frame_duration_us or self.exposure_us) / 1_000_000.0
        )
        self._nr_fresh_epoch_deadline_mono = time.monotonic() + frame_duration_s

    def is_within_fresh_capture_epoch(self) -> bool:
        """当前是否仍处于"下一帧可能不安全"的窗口内 / Whether we're still
        inside the window where the next frame might not be safe yet.

        窗口过后，当前缓存的那一帧本身已经能保证是在上次 settle 之后才开
        始曝光的——调用方（比如一次同姿态内的重试）不需要再等一帧全新的，
        直接用当前缓存的即可，这样重试才不会一直付一次完整曝光的等待成
        本。仅在真正刚发生过 begin_fresh_capture_epoch 之后的短暂窗口内才
        返回 True。
        Once this window has passed, the currently cached frame is already
        guaranteed to have started exposing after the last settle - a
        caller retrying at an unchanged pose doesn't need to wait for
        another brand-new one, it can just use what's cached right now.
        Only returns True for the brief window right after
        begin_fresh_capture_epoch was actually called.
        """
        return time.monotonic() < self._nr_fresh_epoch_deadline_mono

    def stop_capture(self) -> bool:
        """停止抓帧并释放节点以解除阻塞读取 / Stop capture and release the node to unblock reads."""
        self.is_capturing = False
        capture = self._capture
        self._capture = None
        if capture is not None:
            try:
                capture.release()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "释放 V4L2 抓帧节点失败 / Failed to release V4L2 capture: %s", exc
                )
                return False
        return True

    def close(self) -> bool:
        """释放 V4L2 视频节点 / Release the V4L2 video node."""
        self._trace.close()
        released = self.stop_capture()
        self.is_initialized = False
        return released

    def _unpack_raw(self, frame: np.ndarray) -> np.ndarray:
        """将 RG10 容器统一成二维 uint16 / Normalize RG10 containers to 2-D uint16."""
        raw = np.asarray(frame)
        if raw.dtype == np.uint16 and raw.ndim == 2:
            return raw
        if raw.dtype == np.uint8 and raw.ndim == 3 and raw.shape[-1] == 2:
            return np.ascontiguousarray(raw).view("<u2").reshape(raw.shape[:2])
        if raw.dtype == np.uint8 and raw.ndim == 2:
            expected_bytes = self.active_width * self.active_height * 2
            if raw.size == expected_bytes:
                return (
                    np.ascontiguousarray(raw)
                    .reshape(-1)
                    .view("<u2")
                    .reshape(self.active_height, self.active_width)
                )
        raise ValueError(
            f"unsupported RAW frame shape={raw.shape} dtype={raw.dtype} / 不支持的 RAW 帧"
        )

    def _build_gamma_lut(self) -> np.ndarray:
        """构建 RAW 编码值 -> 8 位 gamma 校正输出的查找表 / Build a RAW-code ->
        8-bit gamma-corrected-output lookup table.

        必须在 float32 线性域里对每个 RAW 编码值做 gamma，再量化成 8 位一次；
        如果先线性拉伸到 8 位再查表，暗部（比如星点）在拉伸阶段就已经被压进
        寥寥几个 8 位编码，gamma 再怎么展开也找不回损失的精度。
        Gamma must be applied per RAW code in float32 linear space, quantizing
        to 8-bit only once at the end; linearly stretching to 8-bit first and
        then applying gamma via a 256-entry LUT crushes dim detail (e.g. faint
        stars) into a handful of 8-bit codes before gamma ever sees it, and no
        amount of gamma afterward can recover precision already lost there.

        以 GAMMA_LUT_OVERSAMPLE 倍过采样建表：时域降噪现在在线性 RAW 域做
        （见 _apply_temporal_nr），多帧平均后的 RAW 值带有亚整数精度——实测
        10ms 曝光下输出噪声只有约 0.17 个 RAW 编码值，如果查表前先四舍五入回
        整数，这部分精度会被量化掉，短曝光的降噪效果就白做了。
        The table is oversampled by GAMMA_LUT_OVERSAMPLE: temporal NR now runs
        in the linear RAW domain (see _apply_temporal_nr), so the averaged RAW
        values carry sub-integer precision - measured output noise at 10ms is
        only ~0.17 RAW codes, which rounding to integers before the lookup
        would quantize away, throwing out the short-exposure NR gain.
        """
        max_code = (1 << max(1, self.bit_depth)) - 1
        steps = max_code * GAMMA_LUT_OVERSAMPLE + 1
        codes = np.arange(steps, dtype=np.float32) / GAMMA_LUT_OVERSAMPLE
        span = max(1, self.white_level - self.black_level)
        linear = np.clip((codes - self.black_level) / span, 0.0, 1.0)
        gamma_corrected = np.power(linear, 1.0 / self.gamma) * 255.0
        return np.clip(np.round(gamma_corrected), 0, 255).astype(np.uint8)

    def _debayer(self, raw: np.ndarray) -> np.ndarray:
        """把右对齐 Bayer RAW 转为 RGB888，并做 gamma 校正 / Convert right-aligned
        Bayer RAW to RGB888, gamma-corrected to match ISP-path contrast."""
        import cv2

        lut = self._gamma_lut
        if lut is None:
            lut = self._build_gamma_lut()
            self._gamma_lut = lut
        # 复用预分配缓冲做查表下标，避免每帧新建整幅 float32/int32 临时数组
        # ——这条路径存在的意义就是省内存，每帧分配几个 3.7MB 的临时量会把
        # 峰值 RSS 推上去 / Reuse preallocated buffers for the LUT indices
        # instead of allocating full-frame float32/int32 temporaries every
        # frame - this path exists to save memory, and a few 3.7MB
        # per-frame temporaries push peak RSS up.
        raw_f = np.asarray(raw, dtype=np.float32)
        scratch = self._frame_scratch
        if scratch is None or scratch.shape != raw_f.shape:
            scratch = np.empty(raw_f.shape, dtype=np.float32)
            self._frame_scratch = scratch
        indices = self._lut_index_buffer
        if indices is None or indices.shape != raw_f.shape:
            indices = np.empty(raw_f.shape, dtype=np.uint16)
            self._lut_index_buffer = indices
        np.multiply(raw_f, GAMMA_LUT_OVERSAMPLE, out=scratch)
        np.rint(scratch, out=scratch)
        np.clip(scratch, 0, len(lut) - 1, out=scratch)
        np.copyto(indices, scratch, casting="unsafe")
        raw8 = lut[indices]
        codes = {
            "RGGB": cv2.COLOR_BayerRG2RGB,
            "BGGR": cv2.COLOR_BayerBG2RGB,
            "GRBG": cv2.COLOR_BayerGR2RGB,
            "GBRG": cv2.COLOR_BayerGB2RGB,
        }
        return cv2.cvtColor(raw8, codes[self.bayer_pattern])

    def _observe_auto_exposure(self, raw: np.ndarray) -> None:
        """从当前 RAW 帧更新下一帧曝光 / Update the next-frame exposure from RAW."""
        observed_exposure_us = self.exposure_us
        observed_analogue_gain = self.analogue_gain
        stats = measure_luminance(
            raw,
            bit_depth=self.bit_depth,
            black_level=self.black_level,
            white_level=self.white_level,
            highlight_percentile=self._ae.limits.highlight_percentile,
        )
        decision = self._ae.observe(
            stats,
            exposure_us=self.exposure_us,
            analogue_gain=self.analogue_gain,
        )
        self._last_luminance = {
            "background": decision.background,
            "highlight": decision.highlight,
            "saturation_fraction": decision.saturation_fraction,
            "sample_count": stats.sample_count,
        }
        self._last_ae = {
            "state": decision.state,
            "error_stops": decision.error_stops,
            "changed": decision.changed,
        }
        if decision.changed:
            if not self._apply_exposure_gain(
                decision.exposure_us, decision.analogue_gain
            ):
                self._last_ae = {
                    "state": "control_error",
                    "error_stops": decision.error_stops,
                    "changed": False,
                }
        self._trace.record(
            {
                "stats": asdict(stats),
                "observed": {
                    "exposure_us": observed_exposure_us,
                    "analogue_gain": observed_analogue_gain,
                },
                "decision": asdict(decision),
                "applied": {
                    "requested_exposure_us": self.requested_exposure_us,
                    "requested_analogue_gain": self.requested_analogue_gain,
                    "estimated_exposure_us": self.exposure_us,
                    "estimated_analogue_gain": self.analogue_gain,
                    "actual_exposure_us": self.actual_exposure_us,
                    "actual_analogue_gain": self.actual_analogue_gain,
                    "readback_verified": self._control_readback_verified,
                    "readback_error": self._control_readback_error,
                },
            },
            raw,
        )

    def _white_balance_gains(self) -> tuple[float, float, float]:
        """当前白平衡增益 / Current white-balance gains."""
        if self.white_balance_mode == "night":
            return (1.1, 1.0, 0.9)
        if self.white_balance_mode == "manual":
            return (self.white_balance_gain_r, 1.0, self.white_balance_gain_b)
        return (1.0, 1.0, 1.0)

    def _tone_lut(self) -> np.ndarray:
        """白平衡+对比度+亮度折叠成的 256x3 查找表（按参数缓存）/ The
        white-balance + contrast + brightness chain folded into one 256x3
        LUT, cached against the parameters that define it."""
        key = (
            self._white_balance_gains(),
            self.contrast,
            self.brightness,
        )
        if self._tone_lut_key != key or self._tone_lut_cache is None:
            gains, contrast, brightness = key
            levels = np.arange(256, dtype=np.float32)
            offset = 127.5 * (1.0 - contrast) + brightness * 127.5
            table = np.empty((1, 256, 3), dtype=np.uint8)
            for channel, gain in enumerate(gains):
                values = levels * gain * contrast + offset
                table[0, :, channel] = np.clip(np.rint(values), 0, 255).astype(np.uint8)
            self._tone_lut_cache = table
            self._tone_lut_key = key
        return self._tone_lut_cache

    def _apply_postprocessing(self, image: np.ndarray) -> np.ndarray:
        """应用轻量 RAW 后处理和几何变换 / Apply lightweight RAW post-processing and geometry."""
        import cv2

        # 白平衡增益、对比度、亮度全都是逐像素逐通道的点运算，输入又是 uint8，
        # 所以可以整条折叠成一张 256x3 的查找表，一次 cv2.LUT 搞定 —— 完全不
        # 需要把整幅图转成 float32。原来的写法每帧要产生多个 11MB 的 float32
        # 临时量（astype、减、乘、加、clip 各一份），这条路径本来就是为省内存
        # 存在的。只有饱和度是跨通道运算（要先求通道均值），没法并进查找表，
        # 所以仅在它非默认值时才回退到 float 路径。
        # White-balance gains, contrast and brightness are all pointwise
        # per-channel operations on a uint8 input, so the whole chain folds
        # into one 256x3 lookup table applied by a single cv2.LUT - no
        # full-frame float32 conversion at all. The previous form allocated
        # several 11MB float32 temporaries per frame (astype, subtract,
        # multiply, add, clip), and this path exists to save memory.
        # Saturation is the one cross-channel op (it needs the per-pixel
        # channel mean), so it can't fold into the LUT and only it falls
        # back to the float path.
        if abs(self.saturation - 1.0) <= 1e-3:
            rgb8: np.ndarray = cv2.LUT(image, self._tone_lut())
        else:
            rgb = image.astype(np.float32)
            gains = self._white_balance_gains()
            rgb *= np.asarray(gains, dtype=np.float32)
            np.multiply(rgb, self.contrast, out=rgb)
            np.add(rgb, 127.5 * (1.0 - self.contrast) + self.brightness * 127.5, out=rgb)
            gray = np.mean(rgb, axis=2, keepdims=True)
            np.subtract(rgb, gray, out=rgb)
            np.multiply(rgb, self.saturation, out=rgb)
            np.add(rgb, gray, out=rgb)
            np.clip(rgb, 0, 255, out=rgb)
            rgb8 = rgb.astype(np.uint8)

        if abs(self.sharpness - 1.0) > 1e-3:
            blurred = cv2.GaussianBlur(rgb8, (0, 0), sigmaX=1.0)
            if self.sharpness < 1.0:
                rgb8 = cv2.addWeighted(
                    rgb8, self.sharpness, blurred, 1.0 - self.sharpness, 0.0
                )
            else:
                amount = self.sharpness - 1.0
                rgb8 = cv2.addWeighted(rgb8, 1.0 + amount, blurred, -amount, 0.0)

        if self.color_mode == "mono":
            gray8 = cv2.cvtColor(rgb8, cv2.COLOR_RGB2GRAY)
            rgb8 = cv2.cvtColor(gray8, cv2.COLOR_GRAY2RGB)

        if self.sampling_mode in {"native", "crop"}:
            crop_width = min(self.width, rgb8.shape[1])
            crop_height = min(self.height, rgb8.shape[0])
            left = max(0, (rgb8.shape[1] - crop_width) // 2)
            top = max(0, (rgb8.shape[0] - crop_height) // 2)
            rgb8 = rgb8[top : top + crop_height, left : left + crop_width]
        if (rgb8.shape[1], rgb8.shape[0]) != (self.width, self.height):
            rgb8 = cv2.resize(
                rgb8, (self.width, self.height), interpolation=cv2.INTER_AREA
            )
        if self.rotation in {90, 180, 270}:
            rgb8 = np.rot90(rgb8, self.rotation // 90)
        if self.flip_horizontal and self.flip_vertical:
            rgb8 = cv2.flip(rgb8, -1)
        elif self.flip_horizontal:
            rgb8 = cv2.flip(rgb8, 1)
        elif self.flip_vertical:
            rgb8 = cv2.flip(rgb8, 0)
        return np.ascontiguousarray(rgb8)

    def _apply_temporal_nr(self, raw: np.ndarray) -> np.ndarray:
        """在线性 RAW 域做时域指数滑动平均降噪 / Temporal exponential-moving-
        average denoise, in the linear RAW domain.

        必须在 gamma 之前、线性域里做，原因有三：
        1. 线性域的平均才是无偏的；在 gamma 编码后的值上平均会有系统偏差。
        2. gamma 曲线在暗部斜率最陡（实测 10ms 曝光下约 1.3，接近黑电平时
           可达数十倍），先降噪再过曲线，等于在噪声被放大之前就把它压掉。
        3. 累积器从 H*W*3 的 float32（约 11MB）变成 H*W 的 float32（约
           3.7MB），省下约 7MB —— 这条路径存在的意义就是省内存，所以这不是
           代价而是额外收益。
        Must run before gamma, in linear space, for three reasons:
        1. Averaging is only unbiased in linear space; averaging
           gamma-encoded values introduces a systematic bias.
        2. The gamma curve is steepest in the shadows (measured ~1.3x at
           10ms, tens of times near black), so denoising first means killing
           the noise before the curve amplifies it.
        3. The accumulator shrinks from H*W*3 float32 (~11MB) to H*W float32
           (~3.7MB), saving ~7MB - this path exists to save memory, so that's
           a bonus rather than a cost.

        场景静止/跟踪时有效；曝光/增益一变，`_apply_exposure_gain` 会清空
        累积器，下一帧直接作为新起点，不会把不同亮度的帧混在一起。累积器
        失效期间（见 begin_fresh_capture_epoch）不会立即把下一帧定为新种
        子——要等过一次完整曝光时长，确保这一帧的曝光起始时间确定晚于失
        效点，否则种子本身可能已经带着旧场景的拖线。
        Effective for static/tracked scenes; any exposure/gain change clears
        the accumulator via `_apply_exposure_gain`, so the next frame starts
        fresh instead of blending frames at different brightness levels.
        While the accumulator is invalid (see begin_fresh_capture_epoch),
        the very next frame is not immediately trusted as the new seed -
        one full exposure duration must elapse first, so the eventual seed
        is guaranteed to have started exposing after the invalidation point,
        rather than itself already carrying the old scene's trail.
        """
        if self.temporal_nr_alpha >= 1.0:
            return raw
        accumulator = self._nr_accumulator
        if accumulator is None or accumulator.shape != raw.shape:
            accumulator = np.empty(raw.shape, dtype=np.float32)
            self._nr_accumulator = accumulator
        if not self._nr_accumulator_valid:
            np.copyto(accumulator, raw, casting="unsafe")
            if time.monotonic() >= self._nr_fresh_epoch_deadline_mono:
                self._nr_accumulator_valid = True
            return accumulator
        # 就地更新，复用一块 scratch：acc += alpha * (raw - acc)。写成
        # `alpha * raw + (1-alpha) * acc` 每帧会产生三个整幅 float32 临时量。
        # In-place update against one reused scratch: acc += alpha*(raw-acc).
        # Writing it as `alpha*raw + (1-alpha)*acc` allocates three
        # full-frame float32 temporaries per frame.
        scratch = self._frame_scratch
        if scratch is None or scratch.shape != raw.shape:
            scratch = np.empty(raw.shape, dtype=np.float32)
            self._frame_scratch = scratch
        np.copyto(scratch, raw, casting="unsafe")
        np.subtract(scratch, accumulator, out=scratch)
        np.multiply(scratch, self._effective_temporal_nr_alpha(), out=scratch)
        np.add(accumulator, scratch, out=accumulator)
        return accumulator

    def _effective_temporal_nr_alpha(self) -> float:
        """按帧时长换算实际 EMA 系数 / Frame-duration-aware EMA coefficient.

        平均帧数 = temporal_nr_seconds / 帧时长，夹在 [1, temporal_nr_max_frames]
        之间：短曝光多平均（墙钟代价可忽略），长曝光则自然收敛到很少的帧数。

        这里曾经还夹着一个下界 1/temporal_nr_alpha（=5 帧）：单帧曝光已经逼近
        上限（如 2s）时，仍强制至少平均 5 帧，真实时域积分窗口被拖到 5 倍单帧
        曝光（10s+）。场景完全静止时看不出来，但曝光期间只要有一点残留机械
        振动/未完全静止，就会被拉成远超单帧曝光时长的星轨——这正是"最大自动
        曝光下出现拖线，看起来像几十秒堆栈"的根因。取消这个下界，长曝光按同样
        的时间预算自然收敛到 1 帧（不再额外平均），不再制造超出单帧曝光的
        隐藏积分窗口。
        Frames averaged = temporal_nr_seconds / frame duration, clamped to
        [1, temporal_nr_max_frames]: short exposures average more (negligible
        wall-clock cost); long exposures now naturally converge to very few
        frames.

        This used to also have a floor of 1/temporal_nr_alpha (=5 frames):
        once a single exposure was already near the ceiling (e.g. 2s), it
        still forced averaging at least 5 frames, stretching the real
        temporal integration window to 5x one frame's exposure (10s+).
        Invisible on a perfectly still scene, but any residual mechanical
        settling during that window smears into star trails far longer than
        the single-frame exposure - this was the root cause of "trailing at
        maximum auto exposure, looking like a multi-ten-second stack".
        Removing the floor lets long exposures converge to 1 frame (no extra
        averaging) from the same time budget, instead of manufacturing a
        hidden integration window beyond the single frame's own exposure.
        """
        frame_duration_us = self._frame_duration_us or self.exposure_us
        if self.temporal_nr_seconds <= 0.0 or frame_duration_us <= 0:
            return self.temporal_nr_alpha
        frames = (self.temporal_nr_seconds * 1_000_000.0) / float(frame_duration_us)
        frames = max(1.0, min(float(self.temporal_nr_max_frames), frames))
        return 1.0 / frames

    def capture_image(self) -> np.ndarray | None:
        """抓取一帧并推进软件 AE / Capture one frame and advance software AE."""
        if not self.is_initialized or not self.is_capturing or self._capture is None:
            return None
        try:
            capture = self._capture
            ok, frame = capture.read()
            if not ok or frame is None:
                return None
            if not self.is_capturing:
                return None
            raw = self._unpack_raw(frame)
            # AE 仍然观察未降噪的原始帧，保持已验证的 AE 行为不变 / AE still
            # observes the un-denoised raw frame, keeping the already-validated
            # AE behaviour unchanged.
            self._observe_auto_exposure(raw)
            denoised = self._apply_temporal_nr(raw)
            return self._apply_postprocessing(self._debayer(denoised))
        except Exception as exc:  # noqa: BLE001
            logger.error("V4L2 抓帧失败 / V4L2 capture failed: %s", exc)
            return None

    def get_video_frame(self) -> np.ndarray | None:
        """读取视频帧 / Read a video frame."""
        return self.capture_image()

    def set_auto_exposure(self, enabled: bool) -> bool:
        """切换软件 AE / Toggle software AE."""
        self.auto_exposure = bool(enabled)
        self._ae.set_enabled(self.auto_exposure)
        self._last_ae = {"state": "searching" if enabled else "manual"}
        return True

    def set_auto_exposure_max_us(self, value: int) -> bool:
        """更新软件 AE 最长曝光 / Update maximum software-AE exposure."""
        self.auto_exposure_max_us = max(
            10_000, min(AUTO_EXPOSURE_MAX_CEILING_US, int(value))
        )
        enabled = self.auto_exposure
        self._ae = self._create_auto_exposure()
        self._ae.set_enabled(enabled)
        return True

    def set_exposure(self, exposure_us: int) -> bool:
        """切到手动并设置曝光 / Switch to manual and set exposure."""
        self.set_auto_exposure(False)
        return self._apply_exposure_gain(int(exposure_us), self.analogue_gain)

    def set_gain(self, analogue_gain: float, digital_gain: float = 1.0) -> bool:
        """切到手动并设置模拟增益 / Switch to manual and set analogue gain."""
        self.set_auto_exposure(False)
        self.digital_gain = 1.0
        return self._apply_exposure_gain(self.exposure_us, float(analogue_gain))

    def set_fps(self, fps: int) -> bool:
        """更新交互目标帧率 / Update the interaction target frame rate."""
        self.fps = max(1, int(fps))
        return True

    def set_resolution(self, width: int, height: int, fps: int | None = None) -> bool:
        """更新输出分辨率，RAW 仍全幅采集 / Update output size while retaining full RAW capture."""
        self.width = max(160, int(width))
        self.height = max(120, int(height))
        self.output_width = self.width
        self.output_height = self.height
        if fps is not None:
            self.fps = max(1, int(fps))
        return True

    def set_rotation(self, rotation: int) -> bool:
        """设置旋转 / Set rotation."""
        if int(rotation) not in {0, 90, 180, 270}:
            return False
        self.rotation = int(rotation)
        return True

    def set_flip(self, flip_horizontal: bool, flip_vertical: bool) -> bool:
        """设置镜像 / Set mirroring."""
        self.flip_horizontal = bool(flip_horizontal)
        self.flip_vertical = bool(flip_vertical)
        return True

    def set_sampling_mode(self, mode: str) -> bool:
        """记录输出采样模式 / Record output sampling mode."""
        mode = str(mode).lower()
        if mode not in {"native", "supersample", "crop"}:
            return False
        self.sampling_mode = mode
        return True

    def set_white_balance(
        self, mode: str, gain_r: float = 1.0, gain_b: float = 1.0
    ) -> bool:
        """设置轻量软件白平衡 / Set lightweight software white balance."""
        if mode not in {"manual", "night", "auto"}:
            return False
        self.white_balance_mode = "night" if mode == "auto" else mode
        self.white_balance_gain_r = float(gain_r)
        self.white_balance_gain_b = float(gain_b)
        return True

    def set_image_enhancement(
        self, contrast: float, brightness: float, saturation: float, sharpness: float
    ) -> bool:
        """设置轻量软件图像增强 / Set lightweight software image enhancement."""
        self.contrast = float(contrast)
        self.brightness = float(brightness)
        self.saturation = float(saturation)
        self.sharpness = float(sharpness)
        return True

    def set_noise_reduction(self, level: int) -> bool:
        """兼容旧接口；RAW 路径暂不做时域降噪 / Compat hook; RAW path has no temporal NR yet."""
        self.noise_reduction_mode = "off"
        return int(level) == 0

    def set_noise_reduction_mode(self, mode: str) -> bool:
        """明确 RAW 路径仅支持关闭降噪 / RAW path explicitly supports NR off only."""
        self.noise_reduction_mode = "off"
        return str(mode) == "off"

    def set_ae_flicker_mode(self, mode: str) -> bool:
        """RAW 夜空 AE 不做市电量化 / RAW night AE does not quantize to mains flicker."""
        self.ae_flicker_mode = "off"
        return str(mode).lower() == "off"

    def set_color_mode(self, color_mode: str) -> bool:
        """设置彩色或单色输出 / Set color or monochrome output."""
        if color_mode not in {"color", "mono"}:
            return False
        self.color_mode = color_mode
        return True

    def set_night_mode(self, enabled: bool) -> bool:
        """设置夜间后处理 / Set night post-processing."""
        self.night_mode = bool(enabled)
        self.white_balance_mode = "night" if enabled else "manual"
        return True

    def get_manual_control_ranges(self) -> dict[str, dict[str, Any]]:
        """返回按真实控件换算的手动范围 / Return manual ranges derived from real controls."""
        exposure_control = self._control_ranges.get("exposure")
        gain_control = self._control_ranges.get("analogue_gain")
        min_exposure = 1_000
        max_exposure = self.auto_exposure_max_us
        max_gain = self.auto_gain_max
        if exposure_control is not None:
            min_exposure = int(exposure_control.minimum * self._line_duration_us)
            max_exposure = int(exposure_control.maximum * self._line_duration_us)
        vblank_control = self._control_ranges.get("vertical_blanking")
        if vblank_control is not None:
            max_exposure = int(
                (self.active_height + vblank_control.maximum - 4)
                * self._line_duration_us
            )
        if gain_control is not None:
            max_gain = self._control_to_gain(gain_control.maximum)
        return {
            "exposure_us": {
                "min": max(1, min_exposure),
                "max": max(min_exposure, max_exposure),
                "default": 10_000,
                "step": max(1, int(self._line_duration_us)),
            },
            "analogue_gain": {
                "min": 1.0,
                "max": round(max_gain, 2),
                "default": 1.0,
                "step": 0.1,
            },
            "digital_gain": {
                "min": 1.0,
                "max": 1.0,
                "default": 1.0,
                "step": 0.1,
                "supported": False,
            },
        }

    def get_camera_info(self) -> dict[str, Any]:
        """返回真实驱动、AE 与亮度遥测 / Return truthful driver, AE, and luminance telemetry."""
        optics_width = (
            self.active_width if self.sampling_mode == "supersample" else self.width
        )
        optics_height = (
            self.active_height if self.sampling_mode == "supersample" else self.height
        )
        optics = IMX327_16MM_F14_OPTICS.describe_capture(
            capture_width_px=optics_width,
            capture_height_px=optics_height,
            sampling_mode=self.sampling_mode,
            rotation_deg=self.rotation,
        )
        caps = CameraCapabilities(
            driver=self.driver_name,
            backend=self.backend_name,
            awb_modes=("manual", "night"),
            auto_exposure=True,
            software_auto_exposure=True,
            manual_exposure=True,
            ae_flicker=False,
            noise_reduction_modes=("off",),
            manual_digital_gain=False,
        )
        return {
            "driver": self.driver_name,
            "backend": self.backend_name,
            "sensor": "IMX327",
            "optics": optics,
            "capabilities": {
                "driver": caps.driver,
                "backend": caps.backend,
                "awb_modes": list(caps.awb_modes),
                "auto_exposure": caps.auto_exposure,
                "software_auto_exposure": caps.software_auto_exposure,
                "manual_exposure": caps.manual_exposure,
                "ae_flicker": caps.ae_flicker,
                "noise_reduction_modes": list(caps.noise_reduction_modes),
                "manual_digital_gain": caps.manual_digital_gain,
                "lores_stream": False,
                "autofocus": False,
                "hdr": False,
            },
            "width": self.width,
            "height": self.height,
            "capture_width": self.active_width,
            "capture_height": self.active_height,
            "output_width": self.output_width,
            "output_height": self.output_height,
            "fps": self.fps,
            "exposure_us": self.exposure_us,
            "requested_exposure_us": self.requested_exposure_us,
            "actual_exposure_us": self.actual_exposure_us,
            "frame_duration_us": self._frame_duration_us,
            "analogue_gain": self.analogue_gain,
            "requested_analogue_gain": self.requested_analogue_gain,
            "actual_analogue_gain": self.actual_analogue_gain,
            "digital_gain": 1.0,
            "actual_digital_gain": 1.0,
            "auto_exposure": self.auto_exposure,
            "auto_exposure_engine": "software_night_sky",
            "auto_exposure_max_us": self.auto_exposure_max_us,
            "effective_auto_exposure_max_us": self._ae.limits.max_exposure_us,
            "effective_auto_gain_max": round(self._ae.limits.max_gain, 3),
            "ae_state": self._last_ae.get("state", "starting"),
            "ae_error_stops": self._last_ae.get("error_stops"),
            "luminance_stats": self._last_luminance,
            "signal_levels": {
                "black_level": self.black_level,
                "white_level": self.white_level,
                "sources": self._signal_level_sources,
            },
            "control_readback": {
                "verified": self._control_readback_verified,
                "error": self._control_readback_error,
            },
            "ae_trace": self._trace.status(),
            "line_duration_us": round(self._line_duration_us, 4),
            "line_duration_source": self._line_duration_source,
            "capture_format": self._capture_format,
            "media_pipeline": self._media_pipeline,
            "rotation": self.rotation,
            "flip_horizontal": self.flip_horizontal,
            "flip_vertical": self.flip_vertical,
            "sampling_mode": self.sampling_mode,
            "color_mode": self.color_mode,
            "white_balance_mode": self.white_balance_mode,
            "white_balance_gain_r": self.white_balance_gain_r,
            "white_balance_gain_b": self.white_balance_gain_b,
            "night_mode": self.night_mode,
            "noise_reduction_mode": self.noise_reduction_mode,
            "ae_flicker_mode": self.ae_flicker_mode,
            "control_ranges": self.get_manual_control_ranges(),
        }

    def get_image_quality_metrics(self) -> dict[str, Any]:
        """把软件 AE 统计映射到调试质量接口 / Map software-AE stats to debug quality metrics."""
        return {
            "noise_level": min(1.0, max(0.0, (self.analogue_gain - 1.0) / 15.0)),
            "exposure_adequacy": min(
                1.0,
                float(self._last_luminance.get("highlight", 0.0))
                / max(0.01, self._ae.limits.target_highlight),
            ),
            "gain_level": self.analogue_gain,
            "night_mode": self.night_mode,
            "recommended_adjustments": [self._last_ae.get("state", "starting")],
            "camera_params": self.get_camera_info(),
        }
