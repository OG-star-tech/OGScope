#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
相机驱动模块
支持 Raspberry Pi Zero 2W 的 MIPI CSI 接口 IMX327 相机
"""

import logging
from typing import Optional, Tuple, Dict, Any
import numpy as np
from abc import ABC, abstractmethod

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
    def get_camera_info(self) -> Dict[str, Any]:
        """获取相机信息 / Get camera information"""
        pass


class IMX327MIPICamera(CameraInterface):
    """IMX327 MIPI 相机驱动 - 基于 Picamera2 / IMX327 MIPI camera driver - based on Picamera2"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.camera = None
        self.is_initialized = False
        self.is_capturing = False
        
        # 相机参数 / Camera parameters
        self.width = config.get('width', 640)
        self.height = config.get('height', 360)
        self.fps = config.get('fps', 5)
        self.exposure_us = config.get('exposure_us', 10000)
        self.analogue_gain = config.get('analogue_gain', 1.0)
        self.digital_gain = config.get('digital_gain', 1.0)
        self.auto_exposure = config.get('auto_exposure', False)
        self.auto_gain = config.get('auto_gain', False)
        self.rotation = config.get('rotation', 0)
        self.color_mode = config.get('color_mode', 'color')  # 'color' | 'mono'
        # 采样模式与尺寸（supersample: 采集分辨率可高于输出分辨率） / Sampling mode and size (supersample: acquisition resolution can be higher than output resolution)
        self.sampling_mode = config.get('sampling_mode', 'supersample')  # supersample | native | crop
        
        # 根据采样模式设置捕获和输出分辨率 / Set capture and output resolution according to sampling mode
        if self.sampling_mode == 'supersample':
            # 超采样模式：设置更高的捕获分辨率，输出分辨率为配置的分辨率 / Oversampling mode: Set a higher capture resolution, and the output resolution is the configured resolution
            self.output_width = self.width
            self.output_height = self.height
            # 设置捕获分辨率为更高的分辨率（推荐2x超采样） / Set the capture resolution to a higher resolution (2x oversampling recommended)
            self.capture_width = max(self.width * 2, 1280)  # 至少1280宽度 / At least 1280 width
            self.capture_height = max(self.height * 2, 720)  # 至少720高度 / At least 720 height
            # 确保捕获分辨率为16:9比例 / Make sure the capture resolution is 16:9 ratio
            self._adjust_capture_resolution_to_aspect_ratio()
        else:
            # native/crop模式：捕获和输出分辨率相同 / native/crop mode: capture and output resolutions are the same
            self.capture_width = self.width
            self.capture_height = self.height
            self.output_width = self.width
            self.output_height = self.height
        
        logger.info(f"初始化 IMX327 MIPI 相机: {self.width}x{self.height}@{self.fps}fps")
    
    def _adjust_capture_resolution_to_aspect_ratio(self):
        """调整捕获分辨率为16:9比例 / Adjust capture resolution to 16:9 ratio"""
        target_aspect_ratio = 16.0 / 9.0
        current_aspect_ratio = self.capture_width / self.capture_height
        
        if abs(current_aspect_ratio - target_aspect_ratio) > 0.01:  # 允许小的误差 / Allow small errors
            # 以宽度为准，调整高度 / Adjust height based on width
            self.capture_height = int(self.capture_width / target_aspect_ratio)
            # 确保高度是偶数（某些相机要求） / Make sure the height is an even number (required by some cameras)
            if self.capture_height % 2 != 0:
                self.capture_height += 1
    
    def initialize(self) -> bool:
        """初始化 MIPI 相机 / Initialize MIPI camera"""
        try:
            from picamera2 import Picamera2
            
            self.camera = Picamera2()
            
            # 统一使用RGB888格式，颜色模式转换在图像处理阶段进行 / RGB888 format is uniformly used, and color mode conversion is performed in the image processing stage.
            # 这样可以保持相机配置的一致性，避免格式兼容性问题 / This maintains consistency in camera configuration and avoids format compatibility issues
            main_format = "RGB888"
            
            # 配置相机 / Configure camera
            camera_config = self.camera.create_still_configuration(
                main={"size": (self.capture_width, self.capture_height), "format": main_format},
                raw={"size": (self.capture_width, self.capture_height), "format": "SRGGB12"}
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
            
            self.is_initialized = True
            logger.info("IMX327 MIPI 相机初始化成功")
            return True
            
        except ImportError:
            logger.error("Picamera2 库未安装，请运行: sudo apt install python3-picamera2")
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
                    main={"size": (self.capture_width, self.capture_height), "format": "RGB888"}
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
                    self.camera.set_controls({"AeEnable": True})
                else:
                    controls = {
                        "AeEnable": False,
                        "ExposureTime": self.exposure_us,
                        "AnalogueGain": self.analogue_gain,
                    }
                    try:
                        self.camera.set_controls({**controls, "DigitalGain": self.digital_gain})
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
            
            # 软件降采样（超采样模式） / Software downsampling (oversampling mode)
            try:
                if self.sampling_mode == 'supersample':
                    if (self.output_width, self.output_height) != (self.capture_width, self.capture_height):
                        import cv2
                        original_shape = image.shape[:2]
                        image = cv2.resize(image, (self.output_width, self.output_height), interpolation=cv2.INTER_AREA)
                        logger.debug(f"超采样降采样: {original_shape[1]}x{original_shape[0]} -> {self.output_width}x{self.output_height}")
                    else:
                        logger.debug("超采样模式但输出尺寸与捕获尺寸相同，跳过降采样")
            except Exception as e:
                logger.warning(f"降采样失败（忽略，使用原图）: {e}")

            # 应用旋转 / Apply rotation
            if self.rotation != 0:
                image = self.apply_rotation(image, self.rotation)
            
            # 应用颜色模式转换 / Apply color mode conversion
            if self.color_mode == 'mono' and len(image.shape) == 3:
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

    def get_video_frame(self) -> Optional[np.ndarray]:
        """获取一帧视频图像（用于实时流） / Get a frame of video image (for live streaming)"""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return None
        return self.capture_image()

    def set_resolution(self, width: int, height: int, fps: Optional[int] = None) -> bool:
        """运行时切换分辨率 / Switch resolution at runtime"""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return False
        
        new_w, new_h = int(width), int(height)
        if fps is not None:
            self.fps = int(fps)

        # 检查是否真的需要改变 / Check if changes are really needed
        if self.sampling_mode == 'supersample':
            current_output_w = self.output_width
            current_output_h = self.output_height
            if current_output_w == new_w and current_output_h == new_h:
                # 输出分辨率相同，只需要更新帧率 / The output resolution is the same, only the frame rate needs to be updated
                try:
                    self.camera.set_controls({"FrameRate": self.fps})
                except Exception:
                    pass
                return True
        else:
            current_w = self.width
            current_h = self.height
            if current_w == new_w and current_h == new_h:
                # 分辨率相同，只需要更新帧率 / The resolution is the same, just the frame rate needs to be updated
                try:
                    self.camera.set_controls({"FrameRate": self.fps})
                except Exception:
                    pass
                return True

        was_capturing = self.is_capturing
        try:
            if self.sampling_mode == 'supersample':
                # 超采样模式：只更新输出分辨率 / Supersampling mode: only update output resolution
                self.output_width = new_w
                self.output_height = new_h
                self.width = new_w
                self.height = new_h
                
                # 检查是否需要提升捕获分辨率 / Check if you need to increase the capture resolution
                target_capture_width = max(new_w * 2, 1280)
                target_capture_height = max(new_h * 2, 720)
                need_reconfig = (target_capture_width > self.capture_width) or (target_capture_height > self.capture_height)
                
                if need_reconfig:
                    # 需要提升捕获分辨率 / Need to increase capture resolution
                    if was_capturing:
                        if not self.stop_capture():
                            return False
                    # 设置更高的捕获分辨率（至少2x超采样） / Set higher capture resolution (at least 2x oversampling)
                    self.capture_width = target_capture_width
                    self.capture_height = target_capture_height
                    self._adjust_capture_resolution_to_aspect_ratio()
                else:
                    # 不需要重新配置硬件，只需要更新帧率 / No need to reconfigure hardware, just update frame rate
                    try:
                        self.camera.set_controls({"FrameRate": self.fps})
                    except Exception:
                        pass
                    return True
            else:
                # native/crop模式：捕获和输出分辨率相同 / native/crop mode: capture and output resolutions are the same
                if was_capturing:
                    if not self.stop_capture():
                        return False
                self.capture_width = new_w
                self.capture_height = new_h
                self.output_width = new_w
                self.output_height = new_h
                self.width = new_w
                self.height = new_h

            # 只有在需要重新配置时才调用configure / Only call configure when reconfiguration is required
            try:
                video_config = self.camera.create_video_configuration(
                    main={"size": (self.capture_width, self.capture_height), "format": "RGB888"}
                )
                self.camera.configure(video_config)
            except Exception:
                still_cfg = self.camera.create_still_configuration(
                    main={"size": (self.capture_width, self.capture_height), "format": "RGB888"},
                    raw={"size": (self.capture_width, self.capture_height), "format": "SRGGB12"}
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
                self.camera.set_controls({
                    "AnalogueGain": analogue_gain,
                    "DigitalGain": digital_gain
                })
            except Exception:
                self.camera.set_controls({
                    "AnalogueGain": analogue_gain
                })
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
            self.camera.set_controls({"AeEnable": enabled})
            self.auto_exposure = enabled

            # 关闭自动曝光时，立即重放当前手动参数，确保状态一致 / When auto-exposure is turned off, the current manual parameters are immediately replayed to ensure consistent status.
            if not enabled:
                controls = {
                    "ExposureTime": self.exposure_us,
                    "AnalogueGain": self.analogue_gain,
                }
                try:
                    self.camera.set_controls({**controls, "DigitalGain": self.digital_gain})
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

    def set_sampling_mode(self, mode: str) -> bool:
        """设置采样模式: supersample | native | crop（目前实现 supersample 与 native）"""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return False
            
        if mode not in ['supersample', 'native', 'crop']:
            logger.error(f"不支持的采样模式: {mode}")
            return False
        try:
            old_mode = self.sampling_mode
            self.sampling_mode = mode
            logger.info(f"采样模式从 {old_mode} 切换到: {mode}")
            
            if mode != 'supersample':
                # native/crop 下输出与采集一致 / The output under native/crop is consistent with the collection
                self.capture_width = self.width
                self.capture_height = self.height
                self.output_width = self.width
                self.output_height = self.height
                logger.info(f"非超采样模式，捕获和输出分辨率设置为: {self.output_width}x{self.output_height}")
            else:
                # 超采样模式：设置更高的捕获分辨率 / Oversampling mode: Set higher capture resolution
                self.output_width = self.width
                self.output_height = self.height
                # 设置捕获分辨率为更高的分辨率 / Set the capture resolution to a higher resolution
                self.capture_width = max(self.width * 2, 1280)
                self.capture_height = max(self.height * 2, 720)
                self._adjust_capture_resolution_to_aspect_ratio()
                
                # 记录详细配置信息 / Record detailed configuration information
                logger.info(f"超采样模式激活:")
                logger.info(f"  - 捕获分辨率: {self.capture_width}x{self.capture_height}")
                logger.info(f"  - 输出分辨率: {self.output_width}x{self.output_height}")
                if self.capture_width > self.output_width and self.capture_height > self.output_height:
                    ratio = min(self.capture_width / self.output_width, self.capture_height / self.output_height)
                    logger.info(f"  - 超采样比例: {ratio:.2f}x")
                    if ratio >= 1.5:
                        logger.info("  - 超采样质量: 优秀")
                    elif ratio >= 1.2:
                        logger.info("  - 超采样质量: 良好")
                    else:
                        logger.warning("  - 超采样质量: 较低，建议调整分辨率")
                else:
                    logger.warning("  - 警告: 捕获分辨率不高于输出分辨率，超采样效果有限")
            
            return True
        except Exception as e:
            logger.error(f"设置采样模式失败: {e}")
            return False
    
    def get_camera_info(self) -> Dict[str, Any]:
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
                "width": self.width,
                "height": self.height,
                "sampling_mode": self.sampling_mode,
                "capture_width": self.capture_width,
                "capture_height": self.capture_height,
                "output_width": self.output_width,
                "output_height": self.output_height,
                "color_mode": self.color_mode,
            }
        except Exception as e:
            logger.error(f"获取相机信息失败: {e}")
            return {}
    
    def get_image_quality_metrics(self) -> Dict[str, Any]:
        """获取图像质量指标 / Get image quality metrics"""
        if not self.is_initialized:
            return {
                "noise_level": 0.0,
                "exposure_adequacy": 0.0,
                "gain_level": 0.0,
                "night_mode": False,
                "recommended_adjustments": ["相机未初始化"],
                "camera_params": {}
            }
        
        try:
            # 计算增益水平（模拟增益 + 数字增益） / Calculate gain level (analog gain + digital gain)
            gain_level = self.analogue_gain * self.digital_gain
            
            # 根据曝光时间判断夜间模式 / Determine night mode based on exposure time
            night_mode = self.exposure_us > 30000  # 曝光时间超过30ms认为是夜间模式 / Exposure time longer than 30ms is considered night mode
            
            # 计算曝光充足度（基于曝光时间） / Calculate exposure adequacy (based on exposure time)
            # 假设10ms为基准曝光时间 / Assume 10ms as the base exposure time
            exposure_adequacy = min(1.0, self.exposure_us / 10000.0)
            
            # 计算噪点水平（基于增益和曝光时间） / Calculate noise level (based on gain and exposure time)
            # 增益越高，噪点越多；曝光时间越长，噪点也越多 / The higher the gain, the more noise; the longer the exposure time, the more noise
            noise_level = min(1.0, (gain_level - 1.0) * 0.1 + (self.exposure_us - 10000) / 100000.0)
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
                    "noise_reduction": getattr(self, 'noise_reduction', 0),
                    "width": self.width,
                    "height": self.height,
                    "fps": self.fps,
                    "sampling_mode": self.sampling_mode
                }
            }
            
        except Exception as e:
            logger.error(f"获取图像质量指标失败: {e}")
            return {
                "noise_level": 0.0,
                "exposure_adequacy": 0.0,
                "gain_level": 0.0,
                "night_mode": False,
                "recommended_adjustments": [f"获取质量指标失败: {str(e)}"],
                "camera_params": {}
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
    
    def set_white_balance(self, mode: str, gain_r: float = 1.0, gain_b: float = 1.0) -> bool:
        """设置白平衡模式 / Set white balance mode"""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return False
        
        try:
            if mode == "auto":
                self.camera.set_controls({"AwbEnable": True})
                logger.info("白平衡设置为自动模式")
            elif mode == "manual":
                self.camera.set_controls({
                    "AwbEnable": False,
                    "ColourGains": (gain_r, gain_b)
                })
                logger.info(f"白平衡设置为手动模式: R={gain_r}, B={gain_b}")
            elif mode == "night":
                # 夜间模式：稍微偏暖色调 / Night mode: Slightly warmer tones
                self.camera.set_controls({
                    "AwbEnable": False,
                    "ColourGains": (1.1, 0.9)
                })
                logger.info("白平衡设置为夜间模式")
            else:
                logger.error(f"不支持的白平衡模式: {mode}")
                return False
            
            return True
        except Exception as e:
            logger.error(f"设置白平衡失败: {e}")
            return False
    
    def set_image_enhancement(self, contrast: float = 1.0, brightness: float = 0.0, 
                             saturation: float = 1.0, sharpness: float = 1.0) -> bool:
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
                logger.info(f"图像增强参数设置: 对比度={contrast}, 亮度={brightness}, 饱和度={saturation}, 锐度={sharpness}")
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
                self.camera.set_controls({
                    "ExposureTime": max(self.exposure_us, 30000),  # 至少30ms / At least 30ms
                    "AnalogueGain": max(self.analogue_gain, 4.0),  # 至少4x增益 / At least 4x gain
                    "AwbEnable": False,
                    "ColourGains": (1.1, 0.9),  # 偏暖色调 / warmer tones
                    "NoiseReductionMode": 2  # 中等降噪 / Moderate noise reduction
                })
                logger.info("夜间模式已启用")
            else:
                # 关闭夜间模式：恢复默认设置 / Turn off night mode: restore default settings
                self.camera.set_controls({
                    "ExposureTime": self.exposure_us,
                    "AnalogueGain": self.analogue_gain,
                    "AwbEnable": True,  # 恢复自动白平衡 / Restore automatic white balance
                    "NoiseReductionMode": 0  # 关闭降噪 / Turn off noise reduction
                })
                logger.info("夜间模式已关闭")
            
            return True
        except Exception as e:
            logger.error(f"设置夜间模式失败: {e}")
            return False
    
    def set_color_mode(self, color_mode: str) -> bool:
        """设置颜色模式 - 需要重新初始化相机 / Set color mode - camera reinitialization required"""
        if color_mode not in ['color', 'mono']:
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
                main={"size": (self.capture_width, self.capture_height), "format": main_format},
                raw={"size": (self.capture_width, self.capture_height), "format": "SRGGB12"}
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
    def create_camera(camera_type: str, config: Dict[str, Any]) -> Optional[CameraInterface]:
        """创建相机实例 / Create camera instance"""
        if camera_type == "imx327_mipi":
            return IMX327MIPICamera(config)
        else:
            logger.error(f"不支持的相机类型: {camera_type}")
            return None


# 兼容性函数，用于平滑迁移 / Compatibility function for smooth migration
def create_camera(config: Dict[str, Any]) -> Optional[CameraInterface]:
    """创建相机的便捷函数 / Convenience functions for creating cameras"""
    camera_type = config.get("type", "imx327_mipi")
    return CameraFactory.create_camera(camera_type, config)
