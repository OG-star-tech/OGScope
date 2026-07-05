#!/usr/bin/env python3
"""
相机驱动模块
支持 Raspberry Pi Zero 2W 的 MIPI CSI 接口 IMX327 相机
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

import numpy as np

from ogscope.domain.camera.driver import CameraCapabilities, LinuxpyV4L2Driver

logger = logging.getLogger(__name__)


class CameraInterface(ABC):
    """相机接口抽象类 / Camera interface abstract class"""

    @abstractmethod
    def initialize(self) -> bool:
        """初始化相机 / Initialize camera"""
        pass

    @abstractmethod
    def start_capture(self) -> bool:
        """开始图像捕获 / Start image capture"""
        pass

    @abstractmethod
    def stop_capture(self) -> bool:
        """停止图像捕获 / Stop image capture"""
        pass

    @abstractmethod
    def capture_image(self) -> Optional[np.ndarray]:
        """捕获单张图像 / Capture a single image"""
        pass

    @abstractmethod
    def set_exposure(self, exposure_us: int) -> bool:
        """设置曝光时间 / Set exposure time"""
        pass

    @abstractmethod
    def set_gain(self, analogue_gain: float, digital_gain: float = 1.0) -> bool:
        """设置增益 / Set gain"""
        pass

    @abstractmethod
    def get_camera_info(self) -> dict[str, Any]:
        """获取相机信息 / Get camera information"""
        pass


class IMX327MIPICamera(CameraInterface):
    """IMX327 MIPI 相机驱动 - 基于 Picamera2 / IMX327 MIPI camera driver - based on Picamera2"""

    SENSOR_MAX_WIDTH = 1920
    SENSOR_MAX_HEIGHT = 1020
    PREVIEW_BUFFER_COUNT = 2
    MANUAL_CONTROL_RANGE_DEFAULTS = {
        "ExposureTime": {"min": 1000, "max": 100000, "default": 10000, "step": 1000},
        "AnalogueGain": {"min": 1.0, "max": 16.0, "default": 1.0, "step": 0.1},
        "DigitalGain": {"min": 1.0, "max": 4.0, "default": 1.0, "step": 0.1},
    }

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.camera = None
        self.is_initialized = False
        self.is_capturing = False
        self._last_metadata: dict[str, Any] = {}
        self.driver_name = "picamera2-imx327"
        self.backend_name = "picamera2/libcamera"
        self.output_pixel_format = "RGB888"
        self._frame_duration_limits: tuple[int, int] | None = None
        self._lores_available = False
        self._last_lores_stats: dict[str, Any] = {}

        # 相机参数 / Camera parameters
        requested_width = int(config.get("width", 640))
        requested_height = int(config.get("height", 360))
        self.width, self.height = self._sanitize_output_resolution(
            requested_width, requested_height
        )
        self.fps = config.get("fps", 5)
        self.exposure_us = config.get("exposure_us", 10000)
        self.analogue_gain = config.get("analogue_gain", 1.0)
        self.digital_gain = config.get("digital_gain", 1.0)
        self.auto_exposure = config.get("auto_exposure", False)
        self.auto_gain = config.get("auto_gain", False)
        self.rotation = config.get("rotation", 0)
        # 输出几何镜像（先旋转后镜像，与预览/解算一致）/ Output mirror after rotation
        self.flip_horizontal = bool(config.get("flip_horizontal", False))
        self.flip_vertical = bool(config.get("flip_vertical", False))
        self.color_mode = config.get("color_mode", "color")  # 'color' | 'mono'
        self.white_balance_mode = config.get("white_balance_mode", "auto")
        self.white_balance_gain_r = config.get("white_balance_gain_r", 1.0)
        self.white_balance_gain_b = config.get("white_balance_gain_b", 1.0)
        self.night_mode = bool(config.get("night_mode", False))
        self.auto_exposure_max_us = int(config.get("auto_exposure_max_us", 2_000_000))
        self.ae_flicker_mode = str(config.get("ae_flicker_mode", "off")).lower()
        self.noise_reduction_mode = self._normalize_noise_reduction_mode(
            config.get("noise_reduction_mode", config.get("noise_reduction", "fast"))
        )
        self.lores_enabled = bool(config.get("lores_enabled", True))
        self.lores_width = self._align_even(int(config.get("lores_width", 320)))
        self.lores_height = self._align_even(int(config.get("lores_height", 240)))
        self.lores_format = str(config.get("lores_format", "YUV420"))
        # 采样模式与尺寸（supersample: 采集分辨率可高于输出分辨率） / Sampling mode and size (supersample: acquisition resolution can be higher than output resolution)
        self.sampling_mode = config.get(
            "sampling_mode", "native"
        )  # supersample | native | crop
        (
            self.sampling_mode,
            self.capture_width,
            self.capture_height,
            self.output_width,
            self.output_height,
        ) = self._resolve_sampling_layout(self.sampling_mode, self.width, self.height)

        # 电子极轴镜默认 AE 策略（约 16mm 广角、低帧率夜空）；仍由 libcamera ISP 闭环 / Polar-scope AE defaults (16mm, dark sky; ISP AE loop).
        self.ae_polar_preset = bool(config.get("ae_polar_preset", True))
        self.ae_exposure_value = float(config.get("ae_exposure_value", 0.35))

        # V4L2 直接控制配置（混合模式：V4L2 控制 + picamera2 捕获）/ V4L2 direct control config (hybrid: V4L2 control + picamera2 capture)
        self.use_v4l2_controls = bool(config.get("use_v4l2_controls", True))
        self.v4l2_sensor_subdev = config.get("v4l2_sensor_subdev", "/dev/v4l-subdev1")
        self.v4l2_video_device = config.get("v4l2_video_device", "/dev/video0")
        self._v4l2_available = False
        self._current_vblank = 45  # IMX327 默认最小值 / Default minimum

        # IMX327 传感器参数 / IMX327 sensor parameters
        self.ACTIVE_HEIGHT = 1080
        self.MIN_VBLANK = 45
        self.MAX_VBLANK = 261063
        self.MIN_HBLANK = 280
        self.MAX_HBLANK = 63615
        self.MICROSECONDS_PER_LINE = 0.008  # 8µs per line for IMX327

        logger.info(
            f"初始化 IMX327 MIPI 相机: {self.width}x{self.height}@{self.fps}fps (V4L2直控={'启用' if self.use_v4l2_controls else '禁用'})"
        )

    # ==================== V4L2 Direct Control Methods ====================

    def _check_v4l2_availability(self) -> bool:
        """检查 V4L2 直接控制是否可用 / Check if V4L2 direct control is available"""
        if not self.use_v4l2_controls:
            return False

        import os
        import subprocess

        # 检查设备文件存在 / Check device files exist
        if not os.path.exists(self.v4l2_sensor_subdev):
            logger.debug(f"V4L2 子设备不存在: {self.v4l2_sensor_subdev}")
            return False

        # 检查 v4l2-ctl 可用 / Check v4l2-ctl available
        try:
            result = subprocess.run(
                ["v4l2-ctl", "--version"],
                capture_output=True,
                timeout=2,
                check=False
            )
            if result.returncode != 0:
                logger.debug("v4l2-ctl 不可用")
                return False
        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.debug("v4l2-ctl 未找到或超时")
            return False

        return True

    def _v4l2_get_control(self, v4l2_name: str) -> Optional[int]:
        """读取 V4L2 控制值 / Read V4L2 control value"""
        import subprocess

        try:
            result = subprocess.run(
                ["v4l2-ctl", "-d", self.v4l2_sensor_subdev, "--all"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False
            )
            if result.returncode != 0:
                return None

            # 解析输出查找控制值 / Parse output for control value
            for line in result.stdout.splitlines():
                if v4l2_name.lower() in line.lower() and "value=" in line:
                    try:
                        value_part = line.split("value=")[1].split()[0]
                        return int(value_part)
                    except (IndexError, ValueError):
                        pass
            return None
        except (subprocess.TimeoutExpired, Exception) as e:
            logger.debug(f"读取 V4L2 控制失败 {v4l2_name}: {e}")
            return None

    def _v4l2_set_control(self, v4l2_name: str, value: int) -> bool:
        """设置 V4L2 控制值 / Set V4L2 control value"""
        import subprocess

        try:
            result = subprocess.run(
                ["v4l2-ctl", "-d", self.v4l2_sensor_subdev, f"--set-ctrl={v4l2_name}={value}"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False
            )
            if result.returncode != 0:
                logger.debug(f"V4L2 控制设置失败 {v4l2_name}={value}: {result.stderr.strip()}")
                return False
            return True
        except (subprocess.TimeoutExpired, Exception) as e:
            logger.debug(f"V4L2 控制设置异常 {v4l2_name}={value}: {e}")
            return False

    def _exposure_us_to_lines(self, exposure_us: int) -> int:
        """将曝光时间从微秒转换为行数 / Convert exposure from microseconds to lines"""
        return int(round(exposure_us * 0.001 / self.MICROSECONDS_PER_LINE))

    def _exposure_lines_to_us(self, exposure_lines: int) -> int:
        """将曝光行数转换为微秒 / Convert exposure from lines to microseconds"""
        return int(round(exposure_lines * self.MICROSECONDS_PER_LINE * 1000))

    def _calculate_required_vblank(self, exposure_lines: int) -> int:
        """计算满足曝光需求的最小 vblank / Calculate minimum vblank for exposure"""
        # 曝光最大可达 (ACTIVE_HEIGHT + vblank) 行
        # Max exposure = (ACTIVE_HEIGHT + vblank) lines
        required_vblank = max(
            self.MIN_VBLANK,
            exposure_lines - self.ACTIVE_HEIGHT + 100  # +100 安全边际 / safety margin
        )
        return min(required_vblank, self.MAX_VBLANK)

    def _auto_adjust_vblank_for_exposure(self, exposure_us: int) -> bool:
        """自动调整 vblank 以适应曝光时间（类似 imx327-capture）/ Auto-adjust vblank for exposure (like imx327-capture)"""
        if not self._v4l2_available:
            return False

        exposure_lines = self._exposure_us_to_lines(exposure_us)
        required_vblank = self._calculate_required_vblank(exposure_lines)

        # 总是设置为所需的 vblank（可增可减，避免不必要的慢帧率）
        # Always set to required vblank (increase or decrease to avoid slow frame rates)
        if required_vblank != self._current_vblank:
            if self._v4l2_set_control("vertical_blanking", required_vblank):
                old_vblank = self._current_vblank
                self._current_vblank = required_vblank
                logger.debug(f"自动调整 vblank: {old_vblank} → {required_vblank} (曝光={exposure_us}µs, {exposure_lines}行)")
                return True

        return True

    def _v4l2_set_exposure_direct(self, exposure_us: int) -> bool:
        """使用 V4L2 直接设置曝光（含 vblank 自动调整）/ Set exposure via V4L2 with vblank auto-adjust"""
        if not self._v4l2_available:
            return False

        # 1. 先调整 vblank 以适应曝光 / First adjust vblank for exposure
        if not self._auto_adjust_vblank_for_exposure(exposure_us):
            return False

        # 2. 设置曝光行数 / Set exposure lines
        exposure_lines = self._exposure_us_to_lines(exposure_us)
        max_exposure_lines = self.ACTIVE_HEIGHT + self._current_vblank

        # 限制曝光在有效范围内 / Clamp exposure to valid range
        clamped_lines = max(1, min(exposure_lines, max_exposure_lines))
        if clamped_lines != exposure_lines:
            logger.warning(
                f"曝光超出范围，已限制: {exposure_lines}行 → {clamped_lines}行 "
                f"(最大={max_exposure_lines}, vblank={self._current_vblank})"
            )

        # 设置曝光控制 / Set exposure control
        success = self._v4l2_set_control("exposure", clamped_lines)
        if success:
            actual_us = self._exposure_lines_to_us(clamped_lines)
            logger.info(
                f"V4L2 曝光设置成功: {exposure_us}µs → {clamped_lines}行 "
                f"(实际≈{actual_us}µs, vblank={self._current_vblank})"
            )
        return success

    def _v4l2_set_gain_direct(self, analogue_gain: float) -> bool:
        """使用 V4L2 直接设置模拟增益 / Set analogue gain via V4L2"""
        if not self._v4l2_available:
            return False

        # IMX327 模拟增益范围: 0-98 (对应约 1x-16x)
        # IMX327 analogue gain range: 0-98 (approximately 1x-16x)
        # 简化映射: linear scale from float to 0-98
        gain_value = int(round((analogue_gain - 1.0) * 98.0 / 15.0))
        gain_value = max(0, min(98, gain_value))

        success = self._v4l2_set_control("analogue_gain", gain_value)
        if success:
            logger.info(f"V4L2 增益设置成功: {analogue_gain:.2f} → {gain_value}")
        return success

    # ==================== End V4L2 Direct Control Methods ====================

    @staticmethod
    def _to_number(value: Any) -> Optional[float]:
        try:
            if value is None:
                return None
            if isinstance(value, bool):
                return None
            if isinstance(value, (int, float)):
                return float(value)
            return float(value)
        except (TypeError, ValueError):
            return None

    def _parse_control_descriptor(self, descriptor: Any) -> dict[str, float]:
        parsed: dict[str, float] = {}

        if isinstance(descriptor, dict):
            for key in ("min", "max", "default", "step"):
                numeric_value = self._to_number(descriptor.get(key))
                if numeric_value is not None:
                    parsed[key] = numeric_value
            return parsed

        if isinstance(descriptor, (tuple, list)):
            if len(descriptor) >= 1:
                min_value = self._to_number(descriptor[0])
                if min_value is not None:
                    parsed["min"] = min_value
            if len(descriptor) >= 2:
                max_value = self._to_number(descriptor[1])
                if max_value is not None:
                    parsed["max"] = max_value
            if len(descriptor) >= 3:
                default_value = self._to_number(descriptor[2])
                if default_value is not None:
                    parsed["default"] = default_value
            if len(descriptor) >= 4:
                step_value = self._to_number(descriptor[3])
                if step_value is not None:
                    parsed["step"] = step_value
            return parsed

        for target_key, attr_names in {
            "min": ("min", "minimum", "lower", "lower_bound"),
            "max": ("max", "maximum", "upper", "upper_bound"),
            "default": ("default",),
            "step": ("step", "increment"),
        }.items():
            for attr_name in attr_names:
                raw_value = getattr(descriptor, attr_name, None)
                numeric_value = self._to_number(raw_value)
                if numeric_value is not None:
                    parsed[target_key] = numeric_value
                    break

        return parsed

    def _extract_control_range(
        self, control_name: str, default_range: dict[str, float]
    ) -> dict[str, float]:
        result = dict(default_range)
        if not self.camera:
            return result

        controls = getattr(self.camera, "camera_controls", None) or {}
        descriptor = controls.get(control_name)
        if descriptor is None:
            return result

        parsed = self._parse_control_descriptor(descriptor)
        for key in ("min", "max", "default", "step"):
            if key in parsed:
                result[key] = parsed[key]

        min_value = result.get("min")
        max_value = result.get("max")
        if (
            isinstance(min_value, (int, float))
            and isinstance(max_value, (int, float))
            and min_value > max_value
        ):
            result["min"], result["max"] = max_value, min_value

        return result

    def get_manual_control_ranges(self) -> dict[str, dict[str, Any]]:
        exposure = self._extract_control_range(
            "ExposureTime", self.MANUAL_CONTROL_RANGE_DEFAULTS["ExposureTime"]
        )
        analogue = self._extract_control_range(
            "AnalogueGain", self.MANUAL_CONTROL_RANGE_DEFAULTS["AnalogueGain"]
        )
        digital = self._extract_control_range(
            "DigitalGain", self.MANUAL_CONTROL_RANGE_DEFAULTS["DigitalGain"]
        )
        return {
            "exposure_us": {
                "min": int(round(exposure["min"])),
                "max": int(round(exposure["max"])),
                "default": int(round(exposure["default"])),
                "step": max(1, int(round(exposure.get("step", 1)))),
            },
            "analogue_gain": {
                "min": float(analogue["min"]),
                "max": float(analogue["max"]),
                "default": float(analogue["default"]),
                "step": float(analogue.get("step", 0.1)),
            },
            "digital_gain": {
                "min": float(digital["min"]),
                "max": float(digital["max"]),
                "default": float(digital["default"]),
                "step": float(digital.get("step", 0.1)),
                "supported": "DigitalGain"
                in (getattr(self.camera, "camera_controls", {}) or {}),
            },
        }

    @staticmethod
    def _align_even(value: int) -> int:
        value = max(2, int(value))
        return value if value % 2 == 0 else value - 1

    def _sanitize_output_resolution(self, width: int, height: int) -> tuple[int, int]:
        safe_w = min(self.SENSOR_MAX_WIDTH, max(160, int(width)))
        safe_h = min(self.SENSOR_MAX_HEIGHT, max(120, int(height)))
        safe_w = self._align_even(safe_w)
        safe_h = self._align_even(safe_h)
        if (safe_w, safe_h) != (int(width), int(height)):
            logger.warning(
                f"请求分辨率 {width}x{height} 超出 IMX327 安全范围，已调整为 {safe_w}x{safe_h}"
            )
        return safe_w, safe_h

    def _resolve_sampling_layout(
        self, mode: str, output_width: int, output_height: int
    ) -> tuple[str, int, int, int, int]:
        output_width, output_height = self._sanitize_output_resolution(
            output_width, output_height
        )
        if mode not in {"supersample", "native", "crop"}:
            mode = "native"
        if mode == "supersample":
            # 先采满幅 1920×1020，再经 _resize_preserve_fov 缩到输出（保留整幅视场，非中心裁切）
            # Full sensor readout then letterbox resize to output (full FOV preserved, not center crop).
            capture_w = self.SENSOR_MAX_WIDTH
            capture_h = self.SENSOR_MAX_HEIGHT
        else:
            # native/crop：当前与输出同尺寸采集；视场由 libcamera 传感器模式决定，一般为整幅缩放非裁切
            # native/crop: capture at output size; FOV from sensor mode (typically full-frame scale, not arbitrary crop).
            # 关闭超采样时按输出尺寸采集，减少大帧常驻与重采样开销
            # Capture at output size when supersample is off to reduce RAM and resize cost.
            capture_w = output_width
            capture_h = output_height
        if mode == "supersample" and (
            output_width >= self.SENSOR_MAX_WIDTH
            or output_height >= self.SENSOR_MAX_HEIGHT
        ):
            logger.warning("当前分辨率下超采样无有效增益，自动切换为 native 模式")
            mode = "native"
            capture_w = output_width
            capture_h = output_height
        return mode, capture_w, capture_h, output_width, output_height

    def _resize_preserve_fov(
        self, image: np.ndarray, target_width: int, target_height: int
    ) -> np.ndarray:
        """整幅等比缩放后必要时黑边填充，不裁切画面中心 / Uniform scale + letterbox; no center crop."""
        import cv2

        src_h, src_w = image.shape[:2]
        if src_w == target_width and src_h == target_height:
            return image

        scale = min(target_width / src_w, target_height / src_h)
        resized_w = max(1, int(round(src_w * scale)))
        resized_h = max(1, int(round(src_h * scale)))
        interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
        resized = cv2.resize(image, (resized_w, resized_h), interpolation=interpolation)

        if resized_w == target_width and resized_h == target_height:
            return resized

        pad_x = max(0, target_width - resized_w)
        pad_y = max(0, target_height - resized_h)
        left = pad_x // 2
        right = pad_x - left
        top = pad_y // 2
        bottom = pad_y - top
        border_value = (0, 0, 0) if len(resized.shape) == 3 else 0
        return cv2.copyMakeBorder(
            resized,
            top,
            bottom,
            left,
            right,
            cv2.BORDER_CONSTANT,
            value=border_value,
        )

    def _camera_controls(self) -> dict[str, Any]:
        """读取 libcamera 控制表；测试桩缺失时返回空表 / Read libcamera controls; empty for test doubles."""
        return getattr(self.camera, "camera_controls", None) or {}

    def _control_supported(self, name: str) -> bool:
        """控制项能力检查 / Check whether a camera control is supported."""
        return name in self._camera_controls()

    @staticmethod
    def _normalize_noise_reduction_mode(value: Any) -> str:
        """归一化降噪语义模式 / Normalize semantic noise-reduction mode."""
        if isinstance(value, int):
            return "off" if value <= 0 else "fast" if value <= 2 else "high_quality"
        text = str(value or "fast").strip().lower().replace("-", "_")
        aliases = {"0": "off", "1": "fast", "2": "fast", "3": "high_quality", "4": "high_quality", "hq": "high_quality"}
        text = aliases.get(text, text)
        return text if text in {"off", "fast", "high_quality"} else "fast"

    @staticmethod
    def _enum_value(enum_obj: Any, *names: str) -> Any | None:
        """安全读取 libcamera 枚举值 / Safely read a libcamera enum value."""
        for name in names:
            if hasattr(enum_obj, name):
                return getattr(enum_obj, name)
        return None

    def _target_frame_period_us(self) -> int:
        """目标帧周期 us / Target frame period in microseconds."""
        return max(1, int(round(1_000_000.0 / max(1.0, float(self.fps)))))

    def _compute_frame_duration_limits(self) -> tuple[int, int]:
        """生成帧周期限制；自动曝光允许长曝光降帧 / Build frame-duration limits."""
        target_us = self._target_frame_period_us()
        if self.auto_exposure:
            max_us = max(target_us, int(self.auto_exposure_max_us))
            return target_us, max_us
        fixed_us = max(target_us, int(self.exposure_us))
        return fixed_us, fixed_us

    def _apply_frame_duration_controls(self) -> None:
        """优先应用 FrameDurationLimits，失败时回退 FrameRate / Prefer FrameDurationLimits, fallback to FrameRate."""
        if not self.camera:
            return
        limits = self._compute_frame_duration_limits()
        self._frame_duration_limits = limits
        if self._control_supported("FrameDurationLimits"):
            try:
                self.camera.set_controls({"FrameDurationLimits": limits})
                return
            except Exception as e:
                logger.debug("FrameDurationLimits 未生效，回退 FrameRate: %s", e)
        try:
            self.camera.set_controls({"FrameRate": float(self.fps)})
        except Exception:
            pass

    def _noise_reduction_control_value(self) -> Any:
        """将语义模式映射到 libcamera 降噪枚举/整数 / Map semantic NR mode to libcamera value."""
        try:
            from picamera2 import controls as pcc

            enum_obj = getattr(pcc, "draft", pcc)
            enum_obj = getattr(enum_obj, "NoiseReductionModeEnum", enum_obj)
            if self.noise_reduction_mode == "off":
                val = self._enum_value(enum_obj, "Off")
                return 0 if val is None else val
            if self.noise_reduction_mode == "high_quality":
                val = self._enum_value(enum_obj, "HighQuality", "HighQualityMode")
                return 2 if val is None else val
            val = self._enum_value(enum_obj, "Fast", "Minimal")
            return 1 if val is None else val
        except Exception:
            return {"off": 0, "fast": 1, "high_quality": 2}[self.noise_reduction_mode]

    def _apply_noise_reduction_controls(self) -> None:
        """应用降噪模式；不支持时安全跳过 / Apply NR mode; safely skip unsupported controls."""
        if not self.camera or not self._control_supported("NoiseReductionMode"):
            return
        try:
            self.camera.set_controls(
                {"NoiseReductionMode": self._noise_reduction_control_value()}
            )
        except Exception as e:
            logger.debug("降噪控制未生效 / Noise reduction control skipped: %s", e)

    def _apply_ae_flicker_controls(self) -> None:
        """应用 AE 防闪烁；不支持时安全跳过 / Apply AE flicker controls when supported."""
        if not self.camera:
            return
        mode = str(self.ae_flicker_mode or "off").lower()
        updates: dict[str, Any] = {}
        if self._control_supported("AeFlickerMode"):
            try:
                from picamera2 import controls as pcc

                enum_obj = getattr(pcc, "AeFlickerModeEnum", pcc)
                enum_value = (
                    self._enum_value(enum_obj, "Manual", "FlickerManual")
                    if mode in {"50hz", "60hz"}
                    else self._enum_value(enum_obj, "Off", "FlickerOff")
                )
            except Exception:
                enum_value = None
            # Picamera2/libcamera 版本间枚举名有差异；找不到枚举时用整数 fallback，禁止传 None。
            # Enum names differ across Picamera2/libcamera versions; fall back to ints and never pass None.
            updates["AeFlickerMode"] = (
                enum_value if enum_value is not None else (1 if mode in {"50hz", "60hz"} else 0)
            )
        if mode in {"50hz", "60hz"} and self._control_supported("AeFlickerPeriod"):
            updates["AeFlickerPeriod"] = 10_000 if mode == "50hz" else 8_333
        if updates:
            try:
                self.camera.set_controls(updates)
            except Exception as e:
                logger.debug("AE 防闪烁控制未生效 / AE flicker control skipped: %s", e)

    def _create_video_configuration(self) -> Any:
        """创建含可选 lores 的视频配置 / Create video config with optional lores stream."""
        if not self.camera:
            raise RuntimeError("camera missing")
        main = {"size": (self.capture_width, self.capture_height), "format": "RGB888"}
        if self.lores_enabled:
            try:
                cfg = self.camera.create_video_configuration(
                    main=main,
                    lores={
                        "size": (self.lores_width, self.lores_height),
                        "format": self.lores_format,
                    },
                    buffer_count=self.PREVIEW_BUFFER_COUNT,
                )
                self._lores_available = True
                return cfg
            except Exception as e:
                self._lores_available = False
                logger.debug("lores 流不可用，回退主流配置 / Lores unavailable, fallback: %s", e)
        self._lores_available = False
        return self.camera.create_video_configuration(
            main=main,
            buffer_count=self.PREVIEW_BUFFER_COUNT,
        )

    def _collect_lores_stats(self, request: Any) -> None:
        """从 lores 流提取轻量亮度统计 / Extract lightweight luminance stats from lores stream."""
        if not self._lores_available:
            return
        try:
            lores = request.make_array("lores")
            if lores is None:
                return
            if len(getattr(lores, "shape", ())) == 2 and lores.shape[0] >= self.lores_height:
                y_plane = lores[: self.lores_height, :]
            elif len(getattr(lores, "shape", ())) >= 3:
                y_plane = lores[..., 0]
            else:
                y_plane = lores
            self._last_lores_stats = {
                "mean": float(np.mean(y_plane)),
                "min": int(np.min(y_plane)),
                "max": int(np.max(y_plane)),
            }
        except Exception as e:
            logger.debug("读取 lores 统计失败 / Failed to read lores stats: %s", e)

    def _camera_capabilities(self) -> dict[str, Any]:
        """汇总相机能力供 API/UI 降级 / Summarize camera capabilities for API/UI fallback."""
        cc = self._camera_controls()
        caps = CameraCapabilities(
            driver=self.driver_name,
            backend=self.backend_name,
            lores_stream=bool(self._lores_available),
            lores_width=self.lores_width if self._lores_available else 0,
            lores_height=self.lores_height if self._lores_available else 0,
            lores_format=self.lores_format if self._lores_available else "",
            ae_flicker=("AeFlickerMode" in cc or "AeFlickerPeriod" in cc),
            manual_digital_gain="DigitalGain" in cc,
            autofocus=any(k.startswith("Af") for k in cc),
            hdr=any("Hdr" in k or "HDR" in k for k in cc),
        )
        return {
            "driver": caps.driver,
            "backend": caps.backend,
            "lores_stream": caps.lores_stream,
            "lores_width": caps.lores_width,
            "lores_height": caps.lores_height,
            "lores_format": caps.lores_format,
            "awb_modes": list(caps.awb_modes),
            "ae_flicker": caps.ae_flicker,
            "noise_reduction_modes": list(caps.noise_reduction_modes),
            "manual_digital_gain": caps.manual_digital_gain,
            "autofocus": caps.autofocus,
            "hdr": caps.hdr,
        }

    def _apply_polar_auto_exposure_controls(self) -> None:
        """libcamera AE 预设：暗部优先、矩阵测光、偏长曝光、EV；失败项跳过 / AE preset; skip unsupported controls."""
        if not self.camera or not self.auto_exposure:
            return
        if not self.ae_polar_preset:
            try:
                self._apply_frame_duration_controls()
                self._apply_ae_flicker_controls()
                self.camera.set_controls({"AeEnable": True})
            except Exception as e:
                logger.debug("AeEnable only: %s", e)
            return
        try:
            from picamera2 import controls as pcc
        except ImportError:
            return

        cc = getattr(self.camera, "camera_controls", None) or {}
        updates: dict[str, Any] = {"AeEnable": True}
        if hasattr(pcc, "AeConstraintModeEnum"):
            updates["AeConstraintMode"] = pcc.AeConstraintModeEnum.Shadows
        if hasattr(pcc, "AeMeteringModeEnum"):
            updates["AeMeteringMode"] = pcc.AeMeteringModeEnum.Matrix
        if hasattr(pcc, "AeExposureModeEnum"):
            updates["AeExposureMode"] = pcc.AeExposureModeEnum.Long
        ev = float(self.ae_exposure_value)
        if abs(ev) > 1e-6:
            if "ExposureValue" in cc:
                updates["ExposureValue"] = ev
            elif "Brightness" in cc:
                updates["Brightness"] = max(-1.0, min(1.0, ev * 0.2))

        try:
            self._apply_frame_duration_controls()
            self._apply_ae_flicker_controls()
            self.camera.set_controls(updates)
            logger.info(
                "已应用电子极轴镜 AE 预设 (Shadows/Matrix/Long, EV≈%.2f)",
                ev,
            )
        except Exception as e:
            logger.warning("AE 预设批量设置失败，逐项重试: %s", e)
            for key, val in updates.items():
                if key != "AeEnable" and key not in cc:
                    continue
                try:
                    self.camera.set_controls({key: val})
                except Exception as err:
                    logger.debug("AE 控制 %s 未生效: %s", key, err)

    def _white_balance_controls(self) -> dict[str, Any]:
        """生成白平衡控制；auto 必须真正打开 AWB / Build WB controls; auto must really enable AWB."""
        mode = str(self.white_balance_mode or "auto").lower()
        if mode == "manual":
            return {
                "AwbEnable": False,
                "ColourGains": (
                    float(self.white_balance_gain_r),
                    float(self.white_balance_gain_b),
                ),
            }
        if mode == "night":
            self.white_balance_gain_r = 1.1
            self.white_balance_gain_b = 0.9
            return {"AwbEnable": False, "ColourGains": (1.1, 0.9)}
        updates: dict[str, Any] = {"AwbEnable": True}
        mode_aliases = {
            "auto": "Auto",
            "daylight": "Daylight",
            "cloudy": "Cloudy",
            "tungsten": "Tungsten",
            "fluorescent": "Fluorescent",
            "indoor": "Indoor",
        }
        if mode not in mode_aliases:
            mode = "auto"
        self.white_balance_mode = mode
        if self._control_supported("AwbMode"):
            try:
                from picamera2 import controls as pcc

                enum_obj = getattr(pcc, "AwbModeEnum", pcc)
                enum_value = self._enum_value(enum_obj, mode_aliases[mode])
                if enum_value is not None:
                    updates["AwbMode"] = enum_value
            except Exception:
                pass
        return updates

    def _apply_white_balance_controls(self) -> None:
        """重放白平衡控制，避免配置重建后回到错误状态 / Replay WB controls after reconfiguration."""
        if not self.camera:
            return
        self.camera.set_controls(self._white_balance_controls())

    def initialize(self) -> bool:
        """初始化 MIPI 相机 / Initialize MIPI camera"""
        try:
            from picamera2 import Picamera2

            self.camera = Picamera2()

            # 检查 V4L2 直接控制是否可用 / Check V4L2 direct control availability
            self._v4l2_available = self._check_v4l2_availability()
            if self._v4l2_available:
                logger.info(f"V4L2 直接控制可用: {self.v4l2_sensor_subdev}")
                # 读取当前 vblank 值 / Read current vblank
                current_vblank = self._v4l2_get_control("vertical_blanking")
                if current_vblank is not None:
                    self._current_vblank = current_vblank
                    logger.debug(f"当前 vblank: {self._current_vblank}")
            else:
                logger.info("V4L2 直接控制不可用，使用 picamera2 控制")

            # 配置主流 + 可选 lores 流；RGB888 保证预览/解算色序一致
            # Configure main + optional lores stream; RGB888 keeps preview/solve color order stable.
            camera_config = self._create_video_configuration()

            self.camera.configure(camera_config)

            # 设置相机控制参数 / Set camera control parameters
            # 如果 V4L2 可用，先设置 V4L2 控制，否则使用 picamera2
            # If V4L2 available, set V4L2 controls first, otherwise use picamera2
            if self._v4l2_available and not self.auto_exposure:
                # 使用 V4L2 直接控制设置初始曝光和增益 / Use V4L2 for initial exposure and gain
                self._v4l2_set_exposure_direct(self.exposure_us)
                self._v4l2_set_gain_direct(self.analogue_gain)
            else:
                # 回退到 picamera2 控制 / Fallback to picamera2 controls
                controls = {
                    "ExposureTime": self.exposure_us,
                    "AnalogueGain": self.analogue_gain,
                    "AeEnable": self.auto_exposure,
                }
                controls.update(self._white_balance_controls())
                try:
                    self.camera.set_controls({**controls, "DigitalGain": self.digital_gain})
                except Exception:
                    # DigitalGain 不被支持时，退化为不设置该项 / When DigitalGain is not supported, it will degenerate to not setting this item.
                    self.camera.set_controls(controls)

            if self.auto_exposure:
                self._apply_polar_auto_exposure_controls()
            else:
                self._apply_frame_duration_controls()
            self._apply_noise_reduction_controls()
            self._apply_ae_flicker_controls()

            self.is_initialized = True
            logger.info("IMX327 MIPI 相机初始化成功")
            return True

        except ImportError:
            logger.error(
                "Picamera2 库未安装，请运行: sudo apt install python3-picamera2"
            )
            return False
        except Exception as e:
            logger.error(f"相机初始化失败: {e}")
            return False

    def start_capture(self) -> bool:
        """开始图像捕获 / Start image capture"""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return False

        try:
            # 设置帧周期（优先 FrameDurationLimits） / Set frame period (prefer FrameDurationLimits).
            self._apply_frame_duration_controls()

            # 重新配置后重放曝光控制，避免状态漂移到驱动默认值 / Replay exposure control after reconfiguration to avoid state drift to driver defaults
            try:
                if self.auto_exposure:
                    self._apply_polar_auto_exposure_controls()
                else:
                    controls = {
                        "AeEnable": False,
                        "ExposureTime": self.exposure_us,
                        "AnalogueGain": self.analogue_gain,
                    }
                    try:
                        self.camera.set_controls(
                            {**controls, "DigitalGain": self.digital_gain}
                        )
                    except Exception:
                        self.camera.set_controls(controls)
                self._apply_white_balance_controls()
                self._apply_noise_reduction_controls()
                self._apply_ae_flicker_controls()
            except Exception as e:
                logger.warning(f"重放曝光控制失败，使用驱动默认控制: {e}")

            self.camera.start()
            self.is_capturing = True
            logger.info("相机开始捕获")
            return True
        except Exception as e:
            logger.error(f"启动相机失败: {e}")
            return False

    def stop_capture(self) -> bool:
        """停止图像捕获 / Stop image capture"""
        if not self.is_capturing:
            return True

        try:
            self.camera.stop()
            self.is_capturing = False
            logger.info("相机停止捕获")
            return True
        except Exception as e:
            logger.error(f"停止相机失败: {e}")
            return False

    def capture_image(self) -> Optional[np.ndarray]:
        """捕获单张图像 / Capture a single image"""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return None

        if not self.is_capturing:
            logger.error("相机未在捕获状态")
            return None

        try:
            # 同一请求读取图像与元数据，避免额外等待下一帧
            # Read image and metadata from one request to avoid waiting for another frame.
            request = self.camera.capture_request()
            try:
                image = request.make_array("main")
                self._last_metadata = dict(request.get_metadata() or {})
                self._collect_lores_stats(request)
            finally:
                request.release()

            # 如果是 RAW 格式，需要转换为 RGB / If it is RAW format, it needs to be converted to RGB
            if len(image.shape) == 2:  # RAW 格式 / RAW format
                # 这里需要实现 RAW 到 RGB 的转换 / Here you need to implement RAW to RGB conversion
                # 暂时返回原始数据 / Temporarily return to original data
                pass

            # 输出重采样（仅当采集与输出不一致） / Output resampling only when capture/output differ
            try:
                if (self.output_width, self.output_height) != (
                    image.shape[1],
                    image.shape[0],
                ):
                    original_shape = image.shape[:2]
                    image = self._resize_preserve_fov(
                        image,
                        self.output_width,
                        self.output_height,
                    )
                    logger.debug(
                        f"输出重采样: {original_shape[1]}x{original_shape[0]} -> {self.output_width}x{self.output_height}"
                    )
            except Exception as e:
                logger.warning(f"输出重采样失败（忽略，使用原图）: {e}")

            # 应用旋转 / Apply rotation
            if self.rotation != 0:
                image = self.apply_rotation(image, self.rotation)

            image = self._apply_flip(image)

            # 应用颜色模式转换 / Apply color mode conversion
            if self.color_mode == "mono" and len(image.shape) == 3:
                # 将彩色图像转换为灰度 / Convert color image to grayscale
                import cv2

                gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
                # 转换为3通道灰度图像（保持兼容性） / Convert to 3-channel grayscale image (maintain compatibility)
                image = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
                logger.debug("应用黑白模式转换")

            if isinstance(image, np.ndarray) and not image.flags["C_CONTIGUOUS"]:
                # 旋转/镜像可能产生负 stride 视图，编码器会被迫慢速复制；这里统一整理为连续内存。
                # Rotation/flip may create negative-stride views; make contiguous before encoding/analysis.
                image = np.ascontiguousarray(image)

            return image

        except Exception as e:
            logger.error(f"捕获图像失败: {e}")
            return None

    def apply_rotation(self, image: np.ndarray, rotation: int) -> np.ndarray:
        """应用图像旋转 / Apply image rotation"""
        try:
            if rotation == 90:
                return np.rot90(image, 1)
            elif rotation == 180:
                return np.rot90(image, 2)
            elif rotation == 270:
                return np.rot90(image, 3)
            else:
                return image
        except Exception as e:
            logger.error(f"图像旋转失败: {e}")
            return image

    def _apply_flip(self, image: np.ndarray) -> np.ndarray:
        """水平/垂直镜像 / Horizontal and vertical flip."""
        if not self.flip_horizontal and not self.flip_vertical:
            return image
        try:
            import cv2

            if self.flip_horizontal and self.flip_vertical:
                return cv2.flip(image, -1)
            if self.flip_horizontal:
                return cv2.flip(image, 1)
            return cv2.flip(image, 0)
        except Exception as e:
            logger.error(f"图像镜像失败: {e}")
            return image

    def get_video_frame(self) -> Optional[np.ndarray]:
        """获取一帧视频图像（用于实时流） / Get a frame of video image (for live streaming)"""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return None
        return self.capture_image()

    def set_resolution(
        self, width: int, height: int, fps: Optional[int] = None
    ) -> bool:
        """运行时切换分辨率 / Switch resolution at runtime"""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return False

        new_w, new_h = self._sanitize_output_resolution(int(width), int(height))
        if fps is not None:
            self.fps = int(fps)

        effective_mode, new_capture_w, new_capture_h, new_output_w, new_output_h = (
            self._resolve_sampling_layout(self.sampling_mode, new_w, new_h)
        )
        if (
            self.output_width == new_output_w
            and self.output_height == new_output_h
            and self.capture_width == new_capture_w
            and self.capture_height == new_capture_h
            and self.sampling_mode == effective_mode
        ):
            try:
                self._apply_frame_duration_controls()
            except Exception:
                pass
            return True

        old_capture_w = self.capture_width
        old_capture_h = self.capture_height
        was_capturing = self.is_capturing
        try:
            self.sampling_mode = effective_mode
            self.capture_width = new_capture_w
            self.capture_height = new_capture_h
            self.output_width = new_output_w
            self.output_height = new_output_h
            self.width = new_output_w
            self.height = new_output_h

            need_reconfig = (
                old_capture_w != self.capture_width
                or old_capture_h != self.capture_height
            )
            if need_reconfig:
                if was_capturing and not self.stop_capture():
                    return False
                try:
                    video_config = self._create_video_configuration()
                    self.camera.configure(video_config)
                except Exception:
                    still_cfg = self.camera.create_still_configuration(
                        main={
                            "size": (self.capture_width, self.capture_height),
                            "format": "RGB888",
                        }
                    )
                    self.camera.configure(still_cfg)
            try:
                self._apply_frame_duration_controls()
            except Exception:
                pass
            try:
                self._apply_white_balance_controls()
                self._apply_noise_reduction_controls()
                self._apply_ae_flicker_controls()
            except Exception as e:
                logger.warning(f"重放白平衡控制失败（忽略）: {e}")

            if need_reconfig and was_capturing:
                return self.start_capture()
            return True
        except Exception as e:
            logger.error(f"切换分辨率失败: {e}")
            # 如果发生异常，尝试恢复到之前的状态 / If an exception occurs, try to restore to the previous state
            if was_capturing and not self.is_capturing:
                try:
                    self.start_capture()
                except Exception:
                    pass
            return False

    def set_fps(self, fps: int) -> bool:
        """仅设置帧率；若固件支持则动态生效，否则更新内部值备用 / Only set the frame rate; if the firmware supports it, it will take effect dynamically, otherwise the internal value will be updated for later use."""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return False
        try:
            self.fps = int(max(1, fps))
            self._apply_frame_duration_controls()
            logger.info(f"帧率设置为: {self.fps}fps")
            return True
        except Exception as e:
            logger.error(f"设置帧率失败: {e}")
            return False

    def set_exposure(self, exposure_us: int) -> bool:
        """设置曝光时间 / Set exposure time"""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return False

        try:
            # 尝试使用 V4L2 直接控制 / Try V4L2 direct control first
            if self._v4l2_available:
                v4l2_success = self._v4l2_set_exposure_direct(exposure_us)
                if v4l2_success:
                    self.exposure_us = exposure_us
                    self.auto_exposure = False
                    # 同步到 picamera2 以保持状态一致 / Sync to picamera2 for state consistency
                    try:
                        self.camera.set_controls({"AeEnable": False})
                    except Exception:
                        pass
                    return True
                else:
                    logger.warning("V4L2 曝光设置失败，回退到 picamera2")

            # 回退到 picamera2 控制 / Fallback to picamera2 control
            self.camera.set_controls({"AeEnable": False, "ExposureTime": exposure_us})
            self.exposure_us = exposure_us
            self.auto_exposure = False
            self._apply_frame_duration_controls()
            logger.info(f"曝光时间设置为: {exposure_us}μs (picamera2)")
            return True
        except Exception as e:
            logger.error(f"设置曝光时间失败: {e}")
            return False

    def set_gain(self, analogue_gain: float, digital_gain: float = 1.0) -> bool:
        """设置增益 / Set gain"""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return False

        try:
            # 手动设置增益时显式关闭自动曝光，避免控制冲突 / Explicitly turn off automatic exposure when setting gain manually to avoid control conflicts
            try:
                self.camera.set_controls({"AeEnable": False})
            except Exception:
                pass

            # 尝试使用 V4L2 直接控制模拟增益 / Try V4L2 direct control for analogue gain
            if self._v4l2_available:
                v4l2_success = self._v4l2_set_gain_direct(analogue_gain)
                if v4l2_success:
                    self.analogue_gain = analogue_gain
                    self.digital_gain = digital_gain
                    self.auto_exposure = False
                    # 数字增益仍通过 picamera2 设置（V4L2 不直接支持）/ Digital gain still via picamera2
                    if digital_gain != 1.0:
                        try:
                            self.camera.set_controls({"DigitalGain": digital_gain})
                        except Exception:
                            pass
                    return True
                else:
                    logger.warning("V4L2 增益设置失败，回退到 picamera2")

            # 回退到 picamera2 控制 / Fallback to picamera2 control
            # 优先同时设置，若不支持 DigitalGain 则退化仅设置 AnalogueGain / Priority is given to setting both at the same time. If DigitalGain is not supported, only AnalogueGain is set.
            try:
                self.camera.set_controls(
                    {"AnalogueGain": analogue_gain, "DigitalGain": digital_gain}
                )
            except Exception:
                self.camera.set_controls({"AnalogueGain": analogue_gain})
            self.analogue_gain = analogue_gain
            self.digital_gain = digital_gain
            self.auto_exposure = False
            self._apply_frame_duration_controls()
            logger.info(f"增益设置为: 模拟={analogue_gain}, 数字={digital_gain} (picamera2)")
            return True
        except Exception as e:
            logger.error(f"设置增益失败: {e}")
            return False

    def set_auto_exposure(self, enabled: bool) -> bool:
        """设置自动曝光开关 / Set the automatic exposure switch"""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return False

        try:
            self.auto_exposure = enabled
            if enabled:
                self._apply_polar_auto_exposure_controls()
            else:
                self.camera.set_controls({"AeEnable": False})
            self._apply_frame_duration_controls()

            # 关闭自动曝光时，立即重放当前手动参数，确保状态一致 / When auto-exposure is turned off, the current manual parameters are immediately replayed to ensure consistent status.
            if not enabled:
                controls = {
                    "ExposureTime": self.exposure_us,
                    "AnalogueGain": self.analogue_gain,
                }
                try:
                    self.camera.set_controls(
                        {**controls, "DigitalGain": self.digital_gain}
                    )
                except Exception:
                    self.camera.set_controls(controls)

            logger.info(f"自动曝光已{'启用' if enabled else '关闭'}")
            return True
        except Exception as e:
            logger.error(f"设置自动曝光失败: {e}")
            return False

    def set_rotation(self, rotation: int) -> bool:
        """设置图像旋转角度 / Set image rotation angle"""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return False

        if rotation not in [0, 90, 180, 270]:
            logger.error(f"不支持的旋转角度: {rotation}")
            return False

        self.rotation = rotation
        logger.info(f"图像旋转角度设置为: {rotation}度")
        return True

    def set_flip(self, flip_horizontal: bool, flip_vertical: bool) -> bool:
        """设置水平/垂直镜像 / Set horizontal and vertical flip."""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return False
        self.flip_horizontal = bool(flip_horizontal)
        self.flip_vertical = bool(flip_vertical)
        logger.info(
            f"图像镜像: 水平={self.flip_horizontal}, 垂直={self.flip_vertical}"
        )
        return True

    def set_sampling_mode(self, mode: str) -> bool:
        """设置采样模式: supersample | native | crop（目前实现 supersample 与 native）"""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return False

        if mode not in ["supersample", "native", "crop"]:
            logger.error(f"不支持的采样模式: {mode}")
            return False
        try:
            old_mode = self.sampling_mode
            old_capture_w = self.capture_width
            old_capture_h = self.capture_height
            (
                effective_mode,
                capture_w,
                capture_h,
                output_w,
                output_h,
            ) = self._resolve_sampling_layout(mode, self.width, self.height)

            self.sampling_mode = effective_mode
            self.capture_width = capture_w
            self.capture_height = capture_h
            self.output_width = output_w
            self.output_height = output_h
            self.width = output_w
            self.height = output_h
            logger.info(f"采样模式从 {old_mode} 切换到: {self.sampling_mode}")

            need_reconfig = (old_capture_w != self.capture_width) or (
                old_capture_h != self.capture_height
            )
            if not need_reconfig:
                return True

            was_capturing = self.is_capturing
            if was_capturing and not self.stop_capture():
                return False

            try:
                video_config = self._create_video_configuration()
                self.camera.configure(video_config)
            except Exception:
                still_cfg = self.camera.create_still_configuration(
                    main={
                        "size": (self.capture_width, self.capture_height),
                        "format": "RGB888",
                    }
                )
                self.camera.configure(still_cfg)

            try:
                self._apply_frame_duration_controls()
            except Exception:
                pass
            try:
                self._apply_white_balance_controls()
                self._apply_noise_reduction_controls()
                self._apply_ae_flicker_controls()
            except Exception as e:
                logger.warning(f"重放白平衡控制失败（忽略）: {e}")

            if was_capturing:
                return self.start_capture()

            return True
        except Exception as e:
            logger.error(f"设置采样模式失败: {e}")
            return False

    def get_camera_info(self) -> dict[str, Any]:
        """获取相机信息 / Get camera information"""
        if not self.is_initialized:
            return {}

        try:
            camera_properties = self.camera.camera_properties
            metadata = self._last_metadata or {}
            capabilities = self._camera_capabilities()

            # V4L2 直接控制状态 / V4L2 direct control status
            v4l2_info = {
                "v4l2_controls_enabled": self.use_v4l2_controls,
                "v4l2_available": self._v4l2_available,
                "v4l2_sensor_subdev": self.v4l2_sensor_subdev if self._v4l2_available else None,
                "current_vblank": self._current_vblank if self._v4l2_available else None,
                "exposure_lines": self._exposure_us_to_lines(self.exposure_us) if self._v4l2_available else None,
            }

            return {
                "driver": self.driver_name,
                "backend": f"{self.backend_name}+v4l2" if self._v4l2_available else self.backend_name,
                "capabilities": capabilities,
                "v4l2_direct_control": v4l2_info,
                "sensor": camera_properties.get("Model", "Unknown"),
                "resolution": f"{self.width}x{self.height}",
                "fps": self.fps,
                "exposure_us": self.exposure_us,
                "actual_exposure_us": int(
                    metadata.get("ExposureTime", self.exposure_us) or 0
                ),
                "frame_duration_us": int(
                    metadata.get("FrameDuration", 0) or 0
                ),
                "frame_duration_limits": list(
                    self._frame_duration_limits or self._compute_frame_duration_limits()
                ),
                "analogue_gain": self.analogue_gain,
                "digital_gain": self.digital_gain,
                "actual_digital_gain": metadata.get("DigitalGain"),
                "auto_exposure": self.auto_exposure,
                "auto_exposure_max_us": self.auto_exposure_max_us,
                "ae_flicker_mode": self.ae_flicker_mode,
                "noise_reduction_mode": self.noise_reduction_mode,
                "noise_reduction": {"off": 0, "fast": 1, "high_quality": 2}.get(
                    self.noise_reduction_mode, 1
                ),
                "auto_gain": self.auto_gain,
                "rotation": self.rotation,
                "flip_horizontal": self.flip_horizontal,
                "flip_vertical": self.flip_vertical,
                "width": self.width,
                "height": self.height,
                "sampling_mode": self.sampling_mode,
                "capture_width": self.capture_width,
                "capture_height": self.capture_height,
                "output_width": self.output_width,
                "output_height": self.output_height,
                "color_mode": self.color_mode,
                "white_balance_mode": self.white_balance_mode,
                "white_balance_gain_r": self.white_balance_gain_r,
                "white_balance_gain_b": self.white_balance_gain_b,
                "actual_white_balance_gains": metadata.get("ColourGains"),
                "awb_enabled": self.white_balance_mode
                in {"auto", "daylight", "cloudy", "tungsten", "fluorescent", "indoor"},
                "colour_temperature": metadata.get("ColourTemperature"),
                "lux": metadata.get("Lux"),
                "sensor_timestamp": metadata.get("SensorTimestamp"),
                "sensor_black_levels": metadata.get("SensorBlackLevels"),
                "night_mode": self.night_mode,
                "ae_polar_preset": self.ae_polar_preset,
                "ae_exposure_value": self.ae_exposure_value,
                "lores_enabled": self.lores_enabled,
                "lores_available": self._lores_available,
                "lores_width": self.lores_width,
                "lores_height": self.lores_height,
                "lores_format": self.lores_format,
                "lores_stats": self._last_lores_stats,
                "control_ranges": self.get_manual_control_ranges(),
            }
        except Exception as e:
            logger.error(f"获取相机信息失败: {e}")
            return {}

    def get_image_quality_metrics(self) -> dict[str, Any]:
        """获取图像质量指标 / Get image quality metrics"""
        if not self.is_initialized:
            return {
                "noise_level": 0.0,
                "exposure_adequacy": 0.0,
                "gain_level": 0.0,
                "night_mode": False,
                "recommended_adjustments": ["相机未初始化"],
                "camera_params": {},
            }

        try:
            # 计算增益水平（模拟增益 + 数字增益） / Calculate gain level (analog gain + digital gain)
            gain_level = self.analogue_gain * self.digital_gain

            # 根据曝光时间判断夜间模式 / Determine night mode based on exposure time
            night_mode = bool(self.night_mode)

            # 计算曝光充足度（基于曝光时间） / Calculate exposure adequacy (based on exposure time)
            # 假设10ms为基准曝光时间 / Assume 10ms as the base exposure time
            exposure_adequacy = min(1.0, self.exposure_us / 10000.0)

            # 计算噪点水平（基于增益和曝光时间） / Calculate noise level (based on gain and exposure time)
            # 增益越高，噪点越多；曝光时间越长，噪点也越多 / The higher the gain, the more noise; the longer the exposure time, the more noise
            noise_level = min(
                1.0, (gain_level - 1.0) * 0.1 + (self.exposure_us - 10000) / 100000.0
            )
            noise_level = max(0.0, noise_level)

            # 生成调整建议 / Generate adjustment suggestions
            recommendations = []
            if noise_level > 0.7:
                recommendations.append("噪点水平较高，建议降低增益或缩短曝光时间")
            if exposure_adequacy < 0.5:
                recommendations.append("曝光不足，建议增加曝光时间或提高增益")
            if gain_level > 8.0:
                recommendations.append("增益过高，建议降低增益以提高图像质量")
            if not recommendations:
                recommendations.append("图像质量良好，无需调整")

            return {
                "noise_level": round(noise_level, 3),
                "exposure_adequacy": round(exposure_adequacy, 3),
                "gain_level": round(gain_level, 3),
                "night_mode": night_mode,
                "recommended_adjustments": recommendations,
                "camera_params": {
                    "exposure_us": self.exposure_us,
                    "analogue_gain": self.analogue_gain,
                    "digital_gain": self.digital_gain,
                    "noise_reduction": getattr(self, "noise_reduction", 0),
                    "width": self.width,
                    "height": self.height,
                    "fps": self.fps,
                    "sampling_mode": self.sampling_mode,
                },
            }

        except Exception as e:
            logger.error(f"获取图像质量指标失败: {e}")
            return {
                "noise_level": 0.0,
                "exposure_adequacy": 0.0,
                "gain_level": 0.0,
                "night_mode": False,
                "recommended_adjustments": [f"获取质量指标失败: {str(e)}"],
                "camera_params": {},
            }

    def set_noise_reduction(self, level: int) -> bool:
        """兼容旧级别接口并映射到语义模式 / Compat level API mapped to semantic NR mode."""
        return self.set_noise_reduction_mode(self._normalize_noise_reduction_mode(level))

    def set_noise_reduction_mode(self, mode: str) -> bool:
        """设置语义降噪模式 / Set semantic noise-reduction mode."""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return False

        try:
            self.noise_reduction_mode = self._normalize_noise_reduction_mode(mode)
            self._apply_noise_reduction_controls()
            logger.info(f"降噪模式设置为: {self.noise_reduction_mode}")
            return True
        except Exception as e:
            logger.error(f"设置降噪模式失败: {e}")
            return False

    def set_ae_flicker_mode(self, mode: str) -> bool:
        """设置 AE 防闪烁模式 / Set AE flicker mode."""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return False
        text = str(mode or "off").lower().replace("_", "")
        self.ae_flicker_mode = "50hz" if text in {"50", "50hz"} else "60hz" if text in {"60", "60hz"} else "off"
        self._apply_ae_flicker_controls()
        return True

    def set_auto_exposure_max_us(self, value: int) -> bool:
        """设置自动曝光最长帧周期 / Set maximum auto-exposure frame duration."""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return False
        self.auto_exposure_max_us = max(10_000, min(10_000_000, int(value)))
        self._apply_frame_duration_controls()
        return True

    def set_white_balance(
        self, mode: str, gain_r: float = 1.0, gain_b: float = 1.0
    ) -> bool:
        """设置白平衡模式 / Set white balance mode"""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return False

        try:
            mode = str(mode or "auto").lower()
            if mode in {"auto", "daylight", "cloudy", "tungsten", "fluorescent", "indoor"}:
                self.white_balance_mode = mode
                self.white_balance_gain_r = 1.0
                self.white_balance_gain_b = 1.0
                self._apply_white_balance_controls()
                logger.info(f"白平衡设置为模式: {mode}")
            elif mode == "manual":
                self.white_balance_mode = "manual"
                self.white_balance_gain_r = gain_r
                self.white_balance_gain_b = gain_b
                self._apply_white_balance_controls()
                logger.info(f"白平衡设置为手动模式: R={gain_r}, B={gain_b}")
            elif mode == "night":
                # 夜间模式：稍微偏暖色调 / Night mode: Slightly warmer tones
                self.white_balance_mode = "night"
                self._apply_white_balance_controls()
                logger.info("白平衡设置为夜间模式")
            else:
                logger.error(f"不支持的白平衡模式: {mode}")
                return False

            return True
        except Exception as e:
            logger.error(f"设置白平衡失败: {e}")
            return False

    def set_image_enhancement(
        self,
        contrast: float = 1.0,
        brightness: float = 0.0,
        saturation: float = 1.0,
        sharpness: float = 1.0,
    ) -> bool:
        """设置图像增强参数 / Set image enhancement parameters"""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return False

        try:
            # 构建增强参数 / Build enhancement parameters
            enhancement_controls = {}

            # 对比度 (0.5-2.0) / Contrast (0.5-2.0)
            if 0.5 <= contrast <= 2.0:
                enhancement_controls["Contrast"] = contrast

            # 亮度 (-1.0 到 1.0) / Brightness (-1.0 to 1.0)
            if -1.0 <= brightness <= 1.0:
                enhancement_controls["Brightness"] = brightness

            # 饱和度 (0.0-2.0) / Saturation (0.0-2.0)
            if 0.0 <= saturation <= 2.0:
                enhancement_controls["Saturation"] = saturation

            # 锐度 (0.0-2.0) / Sharpness (0.0-2.0)
            if 0.0 <= sharpness <= 2.0:
                enhancement_controls["Sharpness"] = sharpness

            if enhancement_controls:
                self.camera.set_controls(enhancement_controls)
                logger.info(
                    f"图像增强参数设置: 对比度={contrast}, 亮度={brightness}, 饱和度={saturation}, 锐度={sharpness}"
                )
                return True
            else:
                logger.warning("所有增强参数都在有效范围外")
                return False

        except Exception as e:
            logger.error(f"设置图像增强参数失败: {e}")
            return False

    def set_night_mode(self, enabled: bool) -> bool:
        """设置夜间模式 / Set night mode"""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return False

        try:
            if enabled:
                # 夜间模式：提高增益，延长曝光时间，调整白平衡 / Night mode: increase gain, extend exposure time, adjust white balance
                self.exposure_us = max(self.exposure_us, 30000)
                self.analogue_gain = max(self.analogue_gain, 4.0)
                self.white_balance_mode = "night"
                self.noise_reduction_mode = "fast"
                self.camera.set_controls(
                    {
                        "ExposureTime": self.exposure_us,
                        "AnalogueGain": self.analogue_gain,
                    }
                )
                self._apply_white_balance_controls()
                self._apply_noise_reduction_controls()
                self._apply_frame_duration_controls()
                self.night_mode = True
                logger.info("夜间模式已启用")
            else:
                # 关闭夜间模式：恢复默认设置 / Turn off night mode: restore default settings
                self.camera.set_controls(
                    {
                        "ExposureTime": self.exposure_us,
                        "AnalogueGain": self.analogue_gain,
                    }
                )
                self.white_balance_mode = "auto"
                self.white_balance_gain_r = 1.0
                self.white_balance_gain_b = 1.0
                self._apply_white_balance_controls()
                self._apply_noise_reduction_controls()
                self._apply_frame_duration_controls()
                self.night_mode = False
                logger.info("夜间模式已关闭")

            return True
        except Exception as e:
            logger.error(f"设置夜间模式失败: {e}")
            return False

    def set_color_mode(self, color_mode: str) -> bool:
        """设置颜色模式 - 需要重新初始化相机 / Set color mode - camera reinitialization required"""
        if color_mode not in ["color", "mono"]:
            logger.error(f"不支持的颜色模式: {color_mode}")
            return False

        if self.color_mode == color_mode:
            logger.info(f"颜色模式已经是 {color_mode}")
            return True

        try:
            # 停止当前捕获 / Stop current capture
            was_capturing = self.is_capturing
            if was_capturing:
                self.stop_capture()

            # 更新颜色模式 / Update color mode
            self.color_mode = color_mode

            # 颜色模式只影响输出转换，不改变主流 RGB888 配置 / Color mode only changes output conversion.
            camera_config = self._create_video_configuration()

            self.camera.configure(camera_config)
            try:
                self._apply_white_balance_controls()
                self._apply_noise_reduction_controls()
                self._apply_ae_flicker_controls()
                self._apply_frame_duration_controls()
            except Exception as e:
                logger.warning(f"重放白平衡控制失败（忽略）: {e}")

            # 如果之前在捕获，重新开始 / If capturing before, start again
            if was_capturing:
                self.start_capture()

            logger.info(f"颜色模式已切换为: {color_mode}")
            return True

        except Exception as e:
            logger.error(f"设置颜色模式失败: {e}")
            return False


class V4L2Camera(CameraInterface):
    """V4L2-based camera using OpenCV VideoCapture - no picamera2 dependency

    Modular design supporting multiple backends:
    - opencv: Direct OpenCV VideoCapture (default, zero dependencies)
    - gstreamer: GStreamer pipeline via OpenCV (future)
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.backend = config.get("backend", "opencv")  # opencv | gstreamer
        self.device = config.get("device", "/dev/video0")
        self.v4l2_sensor_subdev = config.get("v4l2_sensor_subdev", "/dev/v4l-subdev1")

        # Resolution and capture settings
        self.width = int(config.get("width", 640))
        self.height = int(config.get("height", 480))
        self.fps = int(config.get("fps", 5))
        self.pixel_format = config.get("pixel_format", "RGB3")  # RGB3, YUYV, etc.

        # Exposure and gain settings (V4L2 control via v4l2-ctl)
        self.exposure_us = int(config.get("exposure_us", 10000))
        self.analogue_gain = float(config.get("analogue_gain", 1.0))

        # IMX327 sensor parameters for V4L2 control
        self.ACTIVE_HEIGHT = 1080
        self.MIN_VBLANK = 45
        self.MAX_VBLANK = 261063
        self.MICROSECONDS_PER_LINE = 0.008  # 8µs per line for IMX327
        self._current_vblank = 45

        # Image transformation
        self.rotation = config.get("rotation", 0)
        self.flip_horizontal = bool(config.get("flip_horizontal", False))
        self.flip_vertical = bool(config.get("flip_vertical", False))

        # State
        self.is_initialized = False
        self.is_capturing = False
        self._capture: Optional[Any] = None
        self._v4l2_available = False

        logger.info(
            f"初始化 V4L2 相机: {self.width}x{self.height}@{self.fps}fps, "
            f"设备: {self.device}, 后端: {self.backend}"
        )

    def _configure_media_pipeline(self) -> bool:
        """Configure media controller pipeline for IMX327 sensor (like imx327-capture script)"""
        import subprocess

        try:
            # Configure media pipeline: sensor -> unicam -> video device
            # Use full sensor resolution for media pipeline
            sensor_width = 1920
            sensor_height = 1080
            sensor_format = "SRGGB10_1X10"  # 10-bit Bayer from IMX327

            targets = [
                f'"imx327 10-001a":0[fmt:{sensor_format}/{sensor_width}x{sensor_height}]',
                f'"unicam":0[fmt:{sensor_format}/{sensor_width}x{sensor_height}]',
                f'"unicam":1[fmt:{sensor_format}/{sensor_width}x{sensor_height}]'
            ]

            for target in targets:
                cmd = f'media-ctl -d /dev/media0 --set-v4l2 \'{target}\''
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5, check=False)

                if result.returncode != 0:
                    logger.warning(f"媒体管道配置失败 {target}: {result.stderr.strip()}")
                    return False

                logger.debug(f"媒体管道配置成功: {target}")

            logger.info(f"媒体控制器管道已配置: {sensor_width}x{sensor_height} {sensor_format}")
            return True

        except (subprocess.TimeoutExpired, Exception) as e:
            logger.warning(f"媒体管道配置失败: {e}")
            return False

    def _check_v4l2_controls_availability(self) -> bool:
        """Check if V4L2 sensor controls are available"""
        import os
        import subprocess

        if not os.path.exists(self.v4l2_sensor_subdev):
            logger.debug(f"V4L2 子设备不存在: {self.v4l2_sensor_subdev}")
            return False

        try:
            result = subprocess.run(
                ["v4l2-ctl", "--version"],
                capture_output=True,
                timeout=2,
                check=False
            )
            if result.returncode != 0:
                logger.debug("v4l2-ctl 不可用")
                return False
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.debug("v4l2-ctl 未找到或超时")
            return False

    def _v4l2_set_control(self, v4l2_name: str, value: int) -> bool:
        """Set V4L2 control value using v4l2-ctl"""
        import subprocess

        try:
            result = subprocess.run(
                ["v4l2-ctl", "-d", self.v4l2_sensor_subdev, f"--set-ctrl={v4l2_name}={value}"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False
            )
            if result.returncode != 0:
                logger.debug(f"V4L2 控制设置失败 {v4l2_name}={value}: {result.stderr.strip()}")
                return False
            return True
        except (subprocess.TimeoutExpired, Exception) as e:
            logger.debug(f"V4L2 控制设置异常 {v4l2_name}={value}: {e}")
            return False

    def _exposure_us_to_lines(self, exposure_us: int) -> int:
        """Convert exposure from microseconds to lines"""
        return int(round(exposure_us * 0.001 / self.MICROSECONDS_PER_LINE))

    def _calculate_required_vblank(self, exposure_lines: int) -> int:
        """Calculate minimum vblank for exposure"""
        required_vblank = max(
            self.MIN_VBLANK,
            exposure_lines - self.ACTIVE_HEIGHT + 100  # +100 safety margin
        )
        return min(required_vblank, self.MAX_VBLANK)

    def _auto_adjust_vblank_for_exposure(self, exposure_us: int) -> bool:
        """Auto-adjust vblank to accommodate exposure time"""
        if not self._v4l2_available:
            return False

        exposure_lines = self._exposure_us_to_lines(exposure_us)
        required_vblank = self._calculate_required_vblank(exposure_lines)

        if required_vblank != self._current_vblank:
            if self._v4l2_set_control("vertical_blanking", required_vblank):
                old_vblank = self._current_vblank
                self._current_vblank = required_vblank
                logger.debug(f"自动调整 vblank: {old_vblank} → {required_vblank} (曝光={exposure_us}µs)")
                return True

        return True

    def _create_opencv_capture(self) -> Optional[Any]:
        """Create OpenCV VideoCapture object based on backend (like imx327-capture script)"""
        import cv2

        if self.backend == "opencv":
            # Direct V4L2 capture via OpenCV - use RAW Bayer format
            cap = cv2.VideoCapture(self.device, cv2.CAP_V4L2)

            if not cap.isOpened():
                logger.error(f"无法打开摄像头设备: {self.device}")
                return None

            # Set resolution - use full sensor resolution for capture
            # We'll resize later if needed
            sensor_width = 1920
            sensor_height = 1080

            cap.set(cv2.CAP_PROP_FRAME_WIDTH, sensor_width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, sensor_height)

            # Use RG10 (10-bit Bayer) format - this is what the sensor outputs
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"RG10"))

            # Disable automatic RGB conversion - we'll debayer manually
            cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)

            actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
            fourcc_s = "".join(chr((fourcc >> 8 * i) & 0xFF) for i in range(4))

            logger.info(f"OpenCV VideoCapture 已创建: {actual_w}x{actual_h} [{fourcc_s}] 后端=V4L2")
            return cap

        elif self.backend == "gstreamer":
            # GStreamer pipeline via OpenCV (future implementation)
            pipeline = (
                f"v4l2src device={self.device} ! "
                f"video/x-raw,width={self.width},height={self.height},framerate={self.fps}/1 ! "
                f"videoconvert ! appsink"
            )
            cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)

            if not cap.isOpened():
                logger.error(f"无法创建 GStreamer 管道: {pipeline}")
                return None

            logger.info(f"GStreamer VideoCapture 已创建")
            return cap

        else:
            logger.error(f"不支持的后端: {self.backend}")
            return None

    def initialize(self) -> bool:
        """Initialize V4L2 camera"""
        try:
            # Check V4L2 controls availability
            self._v4l2_available = self._check_v4l2_controls_availability()
            if self._v4l2_available:
                logger.info(f"V4L2 直接控制可用: {self.v4l2_sensor_subdev}")
            else:
                logger.info("V4L2 直接控制不可用")

            # Configure media pipeline BEFORE opening camera (critical for IMX327)
            if not self._configure_media_pipeline():
                logger.warning("媒体管道配置失败，继续尝试打开相机")

            # Create OpenCV capture object
            self._capture = self._create_opencv_capture()
            if not self._capture:
                return False

            # Set initial exposure and gain via V4L2 if available
            if self._v4l2_available:
                self._auto_adjust_vblank_for_exposure(self.exposure_us)
                exposure_lines = self._exposure_us_to_lines(self.exposure_us)
                self._v4l2_set_control("exposure", exposure_lines)

                # IMX327 analogue gain: 0-98 (1x-16x)
                gain_value = int(round((self.analogue_gain - 1.0) * 98.0 / 15.0))
                gain_value = max(0, min(98, gain_value))
                self._v4l2_set_control("analogue_gain", gain_value)

                # Allow camera to settle after control changes (like imx327-capture)
                import time
                settling_time = 0.2
                if self.exposure_us > 1000:  # If exposure > 1ms
                    settling_time += (self.exposure_us * 1e-6) * 3  # Wait 3x exposure time
                logger.debug(f"等待相机稳定 {settling_time:.2f}秒...")
                time.sleep(settling_time)

            self.is_initialized = True
            logger.info("V4L2 相机初始化成功")
            return True

        except Exception as e:
            logger.error(f"V4L2 相机初始化失败: {e}")
            return False

    def start_capture(self) -> bool:
        """Start image capture"""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return False

        # OpenCV VideoCapture starts automatically, just mark as capturing
        self.is_capturing = True
        logger.info("相机开始捕获")
        return True

    def stop_capture(self) -> bool:
        """Stop image capture"""
        if not self.is_capturing:
            return True

        self.is_capturing = False
        logger.info("相机停止捕获")
        return True

    def capture_image(self) -> Optional[np.ndarray]:
        """Capture a single image (like imx327-capture script)"""
        if not self.is_initialized or not self._capture:
            logger.error("相机未初始化")
            return None

        if not self.is_capturing:
            logger.error("相机未在捕获状态")
            return None

        try:
            import cv2

            # Discard first few frames (like imx327-capture does)
            for _ in range(3):
                self._capture.grab()

            # Read raw Bayer frame
            ret, frame = self._capture.read()

            if not ret or frame is None:
                logger.error("读取帧失败")
                return None

            # Process raw Bayer data (10-bit to 8-bit conversion + debayering)
            frame = self._process_raw_frame(frame)

            # Resize to target resolution if needed
            if frame.shape[1] != self.width or frame.shape[0] != self.height:
                frame = cv2.resize(frame, (self.width, self.height), interpolation=cv2.INTER_AREA)

            # Apply rotation
            if self.rotation != 0:
                frame = self._apply_rotation(frame, self.rotation)

            # Apply flip
            frame = self._apply_flip(frame)

            # Ensure contiguous memory for encoder
            if not frame.flags['C_CONTIGUOUS']:
                frame = np.ascontiguousarray(frame)

            return frame

        except Exception as e:
            logger.error(f"捕获图像失败: {e}")
            return None

    def _process_raw_frame(self, frame: np.ndarray) -> np.ndarray:
        """Process raw Bayer frame: reshape, convert to 8-bit, debayer (like imx327-capture)"""
        import cv2

        # Handle different frame shapes from VideoCapture
        if frame.ndim == 2 and frame.shape[0] == 1:
            # Flattened array, reshape to image dimensions
            frame = frame.flatten().view(np.uint16).reshape((1080, 1920))
        elif frame.ndim == 1:
            # 1D array, view as uint16 and reshape
            frame = frame.view(np.uint16).reshape((1080, 1920))
        elif frame.ndim == 3:
            # Already in image format, might need dtype conversion
            if frame.dtype != np.uint16:
                frame = frame.view(np.uint16)

        # Convert 10-bit raw to 8-bit for debayering (right shift by 2 bits)
        raw8 = (frame >> 2).astype(np.uint8) if frame.dtype == np.uint16 else frame

        # Debayer: RG Bayer pattern to BGR
        bgr = cv2.cvtColor(raw8, cv2.COLOR_BayerRG2BGR)

        # Convert BGR to RGB (OGScope expects RGB)
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

        return rgb

    def _apply_rotation(self, image: np.ndarray, rotation: int) -> np.ndarray:
        """Apply image rotation"""
        try:
            if rotation == 90:
                return np.rot90(image, 1)
            elif rotation == 180:
                return np.rot90(image, 2)
            elif rotation == 270:
                return np.rot90(image, 3)
            else:
                return image
        except Exception as e:
            logger.error(f"图像旋转失败: {e}")
            return image

    def _apply_flip(self, image: np.ndarray) -> np.ndarray:
        """Horizontal and vertical flip"""
        if not self.flip_horizontal and not self.flip_vertical:
            return image
        try:
            import cv2
            if self.flip_horizontal and self.flip_vertical:
                return cv2.flip(image, -1)
            if self.flip_horizontal:
                return cv2.flip(image, 1)
            return cv2.flip(image, 0)
        except Exception as e:
            logger.error(f"图像镜像失败: {e}")
            return image

    def set_exposure(self, exposure_us: int) -> bool:
        """Set exposure time via V4L2"""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return False

        if not self._v4l2_available:
            logger.warning("V4L2 控制不可用，无法设置曝光")
            return False

        try:
            # Adjust vblank first
            self._auto_adjust_vblank_for_exposure(exposure_us)

            # Set exposure in lines
            exposure_lines = self._exposure_us_to_lines(exposure_us)
            max_exposure_lines = self.ACTIVE_HEIGHT + self._current_vblank
            clamped_lines = max(1, min(exposure_lines, max_exposure_lines))

            if self._v4l2_set_control("exposure", clamped_lines):
                self.exposure_us = exposure_us
                logger.info(f"V4L2 曝光设置成功: {exposure_us}µs → {clamped_lines}行")
                return True
            return False

        except Exception as e:
            logger.error(f"设置曝光时间失败: {e}")
            return False

    def set_gain(self, analogue_gain: float, digital_gain: float = 1.0) -> bool:
        """Set gain via V4L2 (digital_gain not supported in V4L2-only mode)"""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return False

        if not self._v4l2_available:
            logger.warning("V4L2 控制不可用，无法设置增益")
            return False

        try:
            # IMX327 analogue gain: 0-98 (1x-16x)
            gain_value = int(round((analogue_gain - 1.0) * 98.0 / 15.0))
            gain_value = max(0, min(98, gain_value))

            if self._v4l2_set_control("analogue_gain", gain_value):
                self.analogue_gain = analogue_gain
                logger.info(f"V4L2 增益设置成功: {analogue_gain:.2f} → {gain_value}")
                return True
            return False

        except Exception as e:
            logger.error(f"设置增益失败: {e}")
            return False

    def get_camera_info(self) -> dict[str, Any]:
        """Get camera information"""
        return {
            "driver": "v4l2",
            "backend": self.backend,
            "device": self.device,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "pixel_format": self.pixel_format,
            "exposure_us": self.exposure_us,
            "analogue_gain": self.analogue_gain,
            "is_initialized": self.is_initialized,
            "is_capturing": self.is_capturing,
            "v4l2_available": self._v4l2_available,
        }

    def get_video_frame(self) -> Optional[np.ndarray]:
        """Get a frame of video image (for live streaming)"""
        return self.capture_image()


class CameraFactory:
    """相机工厂类 / Camera factory class"""

    @staticmethod
    def create_camera(
        camera_type: str, config: dict[str, Any]
    ) -> Optional[CameraInterface]:
        """创建相机实例 / Create camera instance"""
        if camera_type == "imx327_mipi":
            return IMX327MIPICamera(config)
        if camera_type == "v4l2":
            return V4L2Camera(config)
        if camera_type in {"linuxpy_v4l2", "v4l2_linuxpy"}:
            # 预留自定义 Linux 入口；树莓派 CSI 默认仍走 Picamera2 / Reserved custom-Linux hook; Pi CSI stays Picamera2.
            return LinuxpyV4L2Driver(config)  # type: ignore[return-value]
        else:
            logger.error(f"不支持的相机类型: {camera_type}")
            return None


# 兼容性函数，用于平滑迁移 / Compatibility function for smooth migration
def create_camera(config: dict[str, Any]) -> Optional[CameraInterface]:
    """创建相机的便捷函数 / Convenience functions for creating cameras"""
    camera_type = config.get("type", "imx327_mipi")
    return CameraFactory.create_camera(camera_type, config)
