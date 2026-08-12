"""V4L2 RAW 相机与夜空软件 AE / V4L2 RAW camera with night-sky software AE."""

from __future__ import annotations

import logging
import math
import re
import subprocess
from dataclasses import dataclass
from typing import Any

import numpy as np

from ogscope.domain.camera.auto_exposure import (
    AutoExposureLimits,
    NightSkyAutoExposure,
    measure_luminance,
)
from ogscope.domain.camera.driver import CameraCapabilities

logger = logging.getLogger(__name__)


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
        self.pixel_format = str(config.get("v4l2_pixel_format", "RG10"))
        self.bit_depth = int(config.get("v4l2_bit_depth", 10))
        self.bayer_pattern = str(config.get("v4l2_bayer_pattern", "RGGB")).upper()
        self.active_width = int(config.get("v4l2_active_width", 1920))
        self.active_height = int(config.get("v4l2_active_height", 1080))
        self.width = int(config.get("width", 1280))
        self.height = int(config.get("height", 720))
        self.fps = max(1, int(config.get("fps", 5)))
        self.rotation = int(config.get("rotation", 0))
        self.flip_horizontal = bool(config.get("flip_horizontal", False))
        self.flip_vertical = bool(config.get("flip_vertical", False))
        self.sampling_mode = str(config.get("sampling_mode", "native"))
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
        self.digital_gain = 1.0
        self.auto_exposure = bool(config.get("auto_exposure", True))
        self.auto_exposure_max_us = int(config.get("auto_exposure_max_us", 2_000_000))
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

        self.is_initialized = False
        self.is_capturing = False
        self._capture: Any | None = None
        self._capture_format: dict[str, Any] = {}
        self._control_ranges: dict[str, V4L2ControlRange] = {}
        self._last_ae: dict[str, Any] = {
            "state": "starting" if self.auto_exposure else "manual"
        }
        self._last_luminance: dict[str, Any] = {}
        self._frame_duration_us = 0
        self._ae = self._create_auto_exposure()
        self._ae.set_enabled(self.auto_exposure)

    def _create_auto_exposure(self) -> NightSkyAutoExposure:
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
                max_gain=max(1.0, float(self.auto_gain_max)),
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

    def _read_control(self, name: str) -> int | None:
        """读取单个整数控件 / Read one integer control."""
        try:
            result = self._run_v4l2(f"--get-ctrl={name}")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0 or ":" not in result.stdout:
            return None
        try:
            return int(result.stdout.rsplit(":", 1)[1].strip())
        except ValueError:
            return None

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
        return 10.0 ** (gain_db / 20.0)

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
        if not self._set_control("exposure", exposure_lines):
            return False
        if not self._set_control("analogue_gain", gain_control):
            return False

        self.exposure_us = max(1, int(round(exposure_lines * self._line_duration_us)))
        self.analogue_gain = round(self._control_to_gain(gain_control), 3)
        frame_lines = self.active_height
        if vblank_control is not None:
            frame_lines += vblank
        self._frame_duration_us = max(
            self.exposure_us, int(round(frame_lines * self._line_duration_us))
        )
        return True

    def _create_capture(self) -> Any | None:
        """打开 V4L2 RAW 视频节点 / Open the V4L2 RAW video node."""
        import cv2

        capture = cv2.VideoCapture(self.device, cv2.CAP_V4L2)
        if not capture.isOpened():
            logger.error(
                "无法打开 V4L2 相机 / Cannot open V4L2 camera: %s", self.device
            )
            return None
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.active_width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.active_height)
        capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*self.pixel_format))
        capture.set(cv2.CAP_PROP_CONVERT_RGB, 0)
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

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
        format_mismatch = actual_fourcc and actual_fourcc != self.pixel_format
        size_mismatch = (
            actual_width > 0
            and actual_height > 0
            and (actual_width, actual_height) != (self.active_width, self.active_height)
        )
        if format_mismatch or size_mismatch:
            logger.error(
                "V4L2 RAW 协商结果不匹配 / Negotiated V4L2 RAW format mismatch: %s",
                self._capture_format,
            )
            capture.release()
            return None
        return capture

    def initialize(self) -> bool:
        """初始化 RAW 抓帧和软件 AE / Initialize RAW capture and software AE."""
        try:
            if not self._discover_control_ranges():
                return False
            self._resolve_line_duration()
            enabled = self.auto_exposure
            self._ae = self._create_auto_exposure()
            self._ae.set_enabled(enabled)
            if not self._apply_exposure_gain(self.exposure_us, self.analogue_gain):
                return False
            self._capture = self._create_capture()
            if self._capture is None:
                return False
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
        if not self.is_initialized or self._capture is None:
            return False
        self.is_capturing = True
        return True

    def stop_capture(self) -> bool:
        """停止消费帧但保留设备热驻留 / Stop consuming frames while keeping the device warm."""
        self.is_capturing = False
        return True

    def close(self) -> None:
        """释放 V4L2 视频节点 / Release the V4L2 video node."""
        self.is_capturing = False
        self.is_initialized = False
        capture = self._capture
        self._capture = None
        if capture is not None:
            try:
                capture.release()
            except Exception:  # noqa: BLE001
                pass

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

    def _debayer(self, raw: np.ndarray) -> np.ndarray:
        """把右对齐 Bayer RAW 转为 RGB888 / Convert right-aligned Bayer RAW to RGB888."""
        import cv2

        shift = max(0, self.bit_depth - 8)
        raw8 = np.clip(raw >> shift, 0, 255).astype(np.uint8)
        codes = {
            "RGGB": cv2.COLOR_BayerRG2RGB,
            "BGGR": cv2.COLOR_BayerBG2RGB,
            "GRBG": cv2.COLOR_BayerGR2RGB,
            "GBRG": cv2.COLOR_BayerGB2RGB,
        }
        return cv2.cvtColor(raw8, codes[self.bayer_pattern])

    def _observe_auto_exposure(self, raw: np.ndarray) -> None:
        """从当前 RAW 帧更新下一帧曝光 / Update the next-frame exposure from RAW."""
        stats = measure_luminance(
            raw,
            bit_depth=self.bit_depth,
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
        if decision.changed and not self._apply_exposure_gain(
            decision.exposure_us, decision.analogue_gain
        ):
            self._last_ae = {
                "state": "control_error",
                "error_stops": decision.error_stops,
                "changed": False,
            }

    def _apply_postprocessing(self, image: np.ndarray) -> np.ndarray:
        """应用轻量 RAW 后处理和几何变换 / Apply lightweight RAW post-processing and geometry."""
        import cv2

        rgb = image.astype(np.float32)
        if self.white_balance_mode == "night":
            gains = (1.1, 1.0, 0.9)
        elif self.white_balance_mode == "manual":
            gains = (self.white_balance_gain_r, 1.0, self.white_balance_gain_b)
        else:
            gains = (1.0, 1.0, 1.0)
        rgb *= np.asarray(gains, dtype=np.float32)
        rgb = (rgb - 127.5) * self.contrast + 127.5 + self.brightness * 127.5

        if abs(self.saturation - 1.0) > 1e-3:
            gray = np.mean(rgb, axis=2, keepdims=True)
            rgb = gray + (rgb - gray) * self.saturation
        rgb8 = np.clip(rgb, 0, 255).astype(np.uint8)

        if self.color_mode == "mono":
            gray8 = cv2.cvtColor(rgb8, cv2.COLOR_RGB2GRAY)
            rgb8 = cv2.cvtColor(gray8, cv2.COLOR_GRAY2RGB)
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

    def capture_image(self) -> np.ndarray | None:
        """抓取一帧并推进软件 AE / Capture one frame and advance software AE."""
        if not self.is_initialized or not self.is_capturing or self._capture is None:
            return None
        try:
            ok, frame = self._capture.read()
            if not ok or frame is None:
                return None
            raw = self._unpack_raw(frame)
            self._observe_auto_exposure(raw)
            return self._apply_postprocessing(self._debayer(raw))
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
        self.auto_exposure_max_us = max(10_000, min(10_000_000, int(value)))
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
            "fps": self.fps,
            "exposure_us": self.exposure_us,
            "actual_exposure_us": self.exposure_us,
            "frame_duration_us": self._frame_duration_us,
            "analogue_gain": self.analogue_gain,
            "actual_analogue_gain": self.analogue_gain,
            "digital_gain": 1.0,
            "actual_digital_gain": 1.0,
            "auto_exposure": self.auto_exposure,
            "auto_exposure_engine": "software_night_sky",
            "auto_exposure_max_us": self.auto_exposure_max_us,
            "effective_auto_exposure_max_us": self._ae.limits.max_exposure_us,
            "ae_state": self._last_ae.get("state", "starting"),
            "ae_error_stops": self._last_ae.get("error_stops"),
            "luminance_stats": self._last_luminance,
            "line_duration_us": round(self._line_duration_us, 4),
            "line_duration_source": self._line_duration_source,
            "capture_format": self._capture_format,
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
