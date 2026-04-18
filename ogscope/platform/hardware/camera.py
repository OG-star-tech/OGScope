#!/usr/bin/env python3
"""
相机驱动模块
支持 Raspberry Pi Zero 2W 的 MIPI CSI 接口 IMX327 相机
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

import numpy as np

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

        logger.info(
            f"初始化 IMX327 MIPI 相机: {self.width}x{self.height}@{self.fps}fps"
        )

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

    def _apply_polar_auto_exposure_controls(self) -> None:
        """libcamera AE 预设：暗部优先、矩阵测光、偏长曝光、EV；失败项跳过 / AE preset; skip unsupported controls."""
        if not self.camera or not self.auto_exposure:
            return
        if not self.ae_polar_preset:
            try:
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

    def initialize(self) -> bool:
        """初始化 MIPI 相机 / Initialize MIPI camera"""
        try:
            from picamera2 import Picamera2

            self.camera = Picamera2()

            # 统一使用RGB888格式，颜色模式转换在图像处理阶段进行 / RGB888 format is uniformly used, and color mode conversion is performed in the image processing stage.
            # 这样可以保持相机配置的一致性，避免格式兼容性问题 / This maintains consistency in camera configuration and avoids format compatibility issues
            main_format = "RGB888"

            # 配置相机 / Configure camera
            camera_config = self.camera.create_video_configuration(
                main={
                    "size": (self.capture_width, self.capture_height),
                    "format": main_format,
                },
                buffer_count=self.PREVIEW_BUFFER_COUNT,
            )

            self.camera.configure(camera_config)

            # 设置相机控制参数 / Set camera control parameters
            # 构建控制参数，兼容部分固件未提供 DigitalGain 的情况 / Build control parameters, compatible with some firmwares that do not provide DigitalGain
            controls = {
                "ExposureTime": self.exposure_us,
                "AnalogueGain": self.analogue_gain,
                "AeEnable": self.auto_exposure,
                "AwbEnable": False,  # 禁用自动白平衡 / Disable automatic white balance
                "NoiseReductionMode": 0,  # 禁用降噪以获得原始数据 / Disable noise reduction to get raw data
            }
            try:
                self.camera.set_controls({**controls, "DigitalGain": self.digital_gain})
            except Exception:
                # DigitalGain 不被支持时，退化为不设置该项 / When DigitalGain is not supported, it will degenerate to not setting this item.
                self.camera.set_controls(controls)

            if self.auto_exposure:
                self._apply_polar_auto_exposure_controls()

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
            # 使用视频配置以获得更高实时性 / Use video configuration for greater real-time performance
            try:
                video_config = self.camera.create_video_configuration(
                    main={
                        "size": (self.capture_width, self.capture_height),
                        "format": "RGB888",
                    },
                    buffer_count=self.PREVIEW_BUFFER_COUNT,
                )
                self.camera.configure(video_config)
            except Exception as e:
                logger.warning(f"视频配置失败，回退到当前配置: {e}")
            # 设置目标帧率（若固件支持） / Set target frame rate (if supported by firmware)
            try:
                self.camera.set_controls({"FrameRate": self.fps})
            except Exception:
                pass

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
            # 捕获图像 / capture image
            image = self.camera.capture_array()

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
                self.camera.set_controls({"FrameRate": self.fps})
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
                    video_config = self.camera.create_video_configuration(
                        main={
                            "size": (self.capture_width, self.capture_height),
                            "format": "RGB888",
                        },
                        buffer_count=self.PREVIEW_BUFFER_COUNT,
                    )
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
                self.camera.set_controls({"FrameRate": self.fps})
            except Exception:
                pass

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
            try:
                self.camera.set_controls({"FrameRate": self.fps})
            except Exception:
                # 不支持动态设置时也返回 True，后续通过重配生效 / True is also returned when dynamic setting is not supported, and will take effect later through reconfiguration.
                pass
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
            self.camera.set_controls({"AeEnable": False, "ExposureTime": exposure_us})
            self.exposure_us = exposure_us
            self.auto_exposure = False
            logger.info(f"曝光时间设置为: {exposure_us}μs")
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
            logger.info(f"增益设置为: 模拟={analogue_gain}, 数字={digital_gain}")
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
                video_config = self.camera.create_video_configuration(
                    main={
                        "size": (self.capture_width, self.capture_height),
                        "format": "RGB888",
                    },
                    buffer_count=self.PREVIEW_BUFFER_COUNT,
                )
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
                self.camera.set_controls({"FrameRate": self.fps})
            except Exception:
                pass

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
            return {
                "sensor": camera_properties.get("Model", "Unknown"),
                "resolution": f"{self.width}x{self.height}",
                "fps": self.fps,
                "exposure_us": self.exposure_us,
                "analogue_gain": self.analogue_gain,
                "digital_gain": self.digital_gain,
                "auto_exposure": self.auto_exposure,
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
                "ae_polar_preset": self.ae_polar_preset,
                "ae_exposure_value": self.ae_exposure_value,
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
            night_mode = (
                self.exposure_us > 30000
            )  # 曝光时间超过30ms认为是夜间模式 / Exposure time longer than 30ms is considered night mode

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
        """设置降噪级别 (0-4) / Set noise reduction level (0-4)"""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return False

        try:
            # 将级别映射到相机控制参数 / Map levels to camera control parameters
            noise_reduction_mode = min(max(level, 0), 4)
            self.camera.set_controls({"NoiseReductionMode": noise_reduction_mode})
            logger.info(f"降噪级别设置为: {noise_reduction_mode}")
            return True
        except Exception as e:
            logger.error(f"设置降噪级别失败: {e}")
            return False

    def set_white_balance(
        self, mode: str, gain_r: float = 1.0, gain_b: float = 1.0
    ) -> bool:
        """设置白平衡模式 / Set white balance mode"""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return False

        try:
            if mode == "auto":
                self.camera.set_controls({"AwbEnable": True})
                self.white_balance_mode = "auto"
                logger.info("白平衡设置为自动模式")
            elif mode == "manual":
                self.camera.set_controls(
                    {"AwbEnable": False, "ColourGains": (gain_r, gain_b)}
                )
                self.white_balance_mode = "manual"
                self.white_balance_gain_r = gain_r
                self.white_balance_gain_b = gain_b
                logger.info(f"白平衡设置为手动模式: R={gain_r}, B={gain_b}")
            elif mode == "night":
                # 夜间模式：稍微偏暖色调 / Night mode: Slightly warmer tones
                self.camera.set_controls(
                    {"AwbEnable": False, "ColourGains": (1.1, 0.9)}
                )
                self.white_balance_mode = "night"
                self.white_balance_gain_r = 1.1
                self.white_balance_gain_b = 0.9
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
                self.camera.set_controls(
                    {
                        "ExposureTime": max(
                            self.exposure_us, 30000
                        ),  # 至少30ms / At least 30ms
                        "AnalogueGain": max(
                            self.analogue_gain, 4.0
                        ),  # 至少4x增益 / At least 4x gain
                        "AwbEnable": False,
                        "ColourGains": (1.1, 0.9),  # 偏暖色调 / warmer tones
                        "NoiseReductionMode": 2,  # 中等降噪 / Moderate noise reduction
                    }
                )
                logger.info("夜间模式已启用")
            else:
                # 关闭夜间模式：恢复默认设置 / Turn off night mode: restore default settings
                self.camera.set_controls(
                    {
                        "ExposureTime": self.exposure_us,
                        "AnalogueGain": self.analogue_gain,
                        "AwbEnable": True,  # 恢复自动白平衡 / Restore automatic white balance
                        "NoiseReductionMode": 0,  # 关闭降噪 / Turn off noise reduction
                    }
                )
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

            # 对于颜色模式，我们统一使用RGB888格式，在图像处理阶段进行转换 / For color mode, we uniformly use the RGB888 format and convert it during the image processing stage.
            # 这样可以保持相机配置的一致性，避免格式兼容性问题 / This maintains consistency in camera configuration and avoids format compatibility issues
            main_format = "RGB888"

            camera_config = self.camera.create_still_configuration(
                main={
                    "size": (self.capture_width, self.capture_height),
                    "format": main_format,
                },
                raw={
                    "size": (self.capture_width, self.capture_height),
                    "format": "SRGGB12",
                },
            )

            self.camera.configure(camera_config)

            # 如果之前在捕获，重新开始 / If capturing before, start again
            if was_capturing:
                self.start_capture()

            logger.info(f"颜色模式已切换为: {color_mode}")
            return True

        except Exception as e:
            logger.error(f"设置颜色模式失败: {e}")
            return False


class CameraFactory:
    """相机工厂类 / Camera factory class"""

    @staticmethod
    def create_camera(
        camera_type: str, config: dict[str, Any]
    ) -> Optional[CameraInterface]:
        """创建相机实例 / Create camera instance"""
        if camera_type == "imx327_mipi":
            return IMX327MIPICamera(config)
        else:
            logger.error(f"不支持的相机类型: {camera_type}")
            return None


# 兼容性函数，用于平滑迁移 / Compatibility function for smooth migration
def create_camera(config: dict[str, Any]) -> Optional[CameraInterface]:
    """创建相机的便捷函数 / Convenience functions for creating cameras"""
    camera_type = config.get("type", "imx327_mipi")
    return CameraFactory.create_camera(camera_type, config)
