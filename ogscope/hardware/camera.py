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
    """相机接口抽象类"""
    
    @abstractmethod
    def initialize(self) -> bool:
        """初始化相机"""
        pass
    
    @abstractmethod
    def start_capture(self) -> bool:
        """开始图像捕获"""
        pass
    
    @abstractmethod
    def stop_capture(self) -> bool:
        """停止图像捕获"""
        pass
    
    @abstractmethod
    def capture_image(self) -> Optional[np.ndarray]:
        """捕获单张图像"""
        pass
    
    @abstractmethod
    def set_exposure(self, exposure_us: int) -> bool:
        """设置曝光时间"""
        pass
    
    @abstractmethod
    def set_gain(self, analogue_gain: float, digital_gain: float = 1.0) -> bool:
        """设置增益"""
        pass
    
    @abstractmethod
    def get_camera_info(self) -> Dict[str, Any]:
        """获取相机信息"""
        pass


class IMX327MIPICamera(CameraInterface):
    """IMX327 MIPI 相机驱动 - 基于 Picamera2"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.camera = None
        self.is_initialized = False
        self.is_capturing = False
        
        # 相机参数
        self.width = config.get('width', 640)
        self.height = config.get('height', 360)
        self.fps = config.get('fps', 5)
        self.exposure_us = config.get('exposure_us', 10000)
        self.analogue_gain = config.get('analogue_gain', 1.0)
        self.digital_gain = config.get('digital_gain', 1.0)
        self.auto_exposure = config.get('auto_exposure', False)
        self.auto_gain = config.get('auto_gain', False)
        self.rotation = config.get('rotation', 0)
        # 采样模式与尺寸（supersample: 采集分辨率可高于输出分辨率）
        self.sampling_mode = config.get('sampling_mode', 'supersample')  # supersample | native | crop
        
        # 根据采样模式设置捕获和输出分辨率
        if self.sampling_mode == 'supersample':
            # 超采样模式：设置更高的捕获分辨率，输出分辨率为配置的分辨率
            self.output_width = self.width
            self.output_height = self.height
            # 设置捕获分辨率为更高的分辨率（推荐2x超采样）
            self.capture_width = max(self.width * 2, 1280)  # 至少1280宽度
            self.capture_height = max(self.height * 2, 720)  # 至少720高度
            # 确保捕获分辨率为16:9比例
            self._adjust_capture_resolution_to_aspect_ratio()
        else:
            # native/crop模式：捕获和输出分辨率相同
            self.capture_width = self.width
            self.capture_height = self.height
            self.output_width = self.width
            self.output_height = self.height
        
        logger.info(f"初始化 IMX327 MIPI 相机: {self.width}x{self.height}@{self.fps}fps")
    
    def _adjust_capture_resolution_to_aspect_ratio(self):
        """调整捕获分辨率为16:9比例"""
        target_aspect_ratio = 16.0 / 9.0
        current_aspect_ratio = self.capture_width / self.capture_height
        
        if abs(current_aspect_ratio - target_aspect_ratio) > 0.01:  # 允许小的误差
            # 以宽度为准，调整高度
            self.capture_height = int(self.capture_width / target_aspect_ratio)
            # 确保高度是偶数（某些相机要求）
            if self.capture_height % 2 != 0:
                self.capture_height += 1
    
    def initialize(self) -> bool:
        """初始化 MIPI 相机"""
        try:
            from picamera2 import Picamera2
            
            self.camera = Picamera2()
            
            # 配置相机
            camera_config = self.camera.create_still_configuration(
                main={"size": (self.capture_width, self.capture_height), "format": "RGB888"},
                raw={"size": (self.capture_width, self.capture_height), "format": "SRGGB12"}
            )
            
            self.camera.configure(camera_config)
            
            # 设置相机控制参数
            # 构建控制参数，兼容部分固件未提供 DigitalGain 的情况
            controls = {
                "ExposureTime": self.exposure_us,
                "AnalogueGain": self.analogue_gain,
                "AeEnable": self.auto_exposure,
                "AwbEnable": False,  # 禁用自动白平衡
                "NoiseReductionMode": 0,  # 禁用降噪以获得原始数据
            }
            try:
                self.camera.set_controls({**controls, "DigitalGain": self.digital_gain})
            except Exception:
                # DigitalGain 不被支持时，退化为不设置该项
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
        """开始图像捕获"""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return False
        
        try:
            # 使用视频配置以获得更高实时性
            try:
                video_config = self.camera.create_video_configuration(
                    main={"size": (self.capture_width, self.capture_height), "format": "RGB888"}
                )
                self.camera.configure(video_config)
            except Exception as e:
                logger.warning(f"视频配置失败，回退到当前配置: {e}")
            # 设置目标帧率（若固件支持）
            try:
                self.camera.set_controls({"FrameRate": self.fps})
            except Exception:
                pass
            self.camera.start()
            self.is_capturing = True
            logger.info("相机开始捕获")
            return True
        except Exception as e:
            logger.error(f"启动相机失败: {e}")
            return False
    
    def stop_capture(self) -> bool:
        """停止图像捕获"""
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
        """捕获单张图像"""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return None
            
        if not self.is_capturing:
            logger.error("相机未在捕获状态")
            return None
        
        try:
            # 捕获图像
            image = self.camera.capture_array()
            
            # 如果是 RAW 格式，需要转换为 RGB
            if len(image.shape) == 2:  # RAW 格式
                # 这里需要实现 RAW 到 RGB 的转换
                # 暂时返回原始数据
                pass
            
            # 软件降采样（超采样模式）
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

            # 应用旋转
            if self.rotation != 0:
                image = self.apply_rotation(image, self.rotation)
            
            return image
            
        except Exception as e:
            logger.error(f"捕获图像失败: {e}")
            return None

    def apply_rotation(self, image: np.ndarray, rotation: int) -> np.ndarray:
        """应用图像旋转"""
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
        """获取一帧视频图像（用于实时流）"""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return None
        return self.capture_image()

    def set_resolution(self, width: int, height: int, fps: Optional[int] = None) -> bool:
        """运行时切换分辨率/帧率；在 supersample 下优先仅调整输出尺寸，必要时才重配硬件"""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return False
        
        was_capturing = self.is_capturing
        try:
            new_w, new_h = int(width), int(height)
            if fps is not None:
                self.fps = int(fps)

            if self.sampling_mode == 'supersample':
                # 超采样模式：只更新输出分辨率
                self.output_width = new_w
                self.output_height = new_h
                self.width = new_w
                self.height = new_h
                
                # 检查是否需要提升捕获分辨率
                target_capture_width = max(new_w * 2, 1280)
                target_capture_height = max(new_h * 2, 720)
                need_reconfig = (target_capture_width > self.capture_width) or (target_capture_height > self.capture_height)
                if not need_reconfig:
                    # 不需要重新配置硬件，只需要更新帧率
                    try:
                        self.camera.set_controls({"FrameRate": self.fps})
                    except Exception:
                        pass
                    return True
                else:
                    # 需要提升捕获分辨率
                    if was_capturing:
                        if not self.stop_capture():
                            return False
                    # 设置更高的捕获分辨率（至少2x超采样）
                    self.capture_width = target_capture_width
                    self.capture_height = target_capture_height
                    self._adjust_capture_resolution_to_aspect_ratio()
            else:
                # native/crop模式：捕获和输出分辨率相同
                if was_capturing:
                    if not self.stop_capture():
                        return False
                self.capture_width = new_w
                self.capture_height = new_h
                self.output_width = new_w
                self.output_height = new_h
                self.width = new_w
                self.height = new_h

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
            # 如果发生异常，尝试恢复到之前的状态
            if was_capturing and not self.is_capturing:
                try:
                    self.start_capture()
                except Exception:
                    pass
            return False

    def set_fps(self, fps: int) -> bool:
        """仅设置帧率；若固件支持则动态生效，否则更新内部值备用"""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return False
        try:
            self.fps = int(max(1, fps))
            try:
                self.camera.set_controls({"FrameRate": self.fps})
            except Exception:
                # 不支持动态设置时也返回 True，后续通过重配生效
                pass
            logger.info(f"帧率设置为: {self.fps}fps")
            return True
        except Exception as e:
            logger.error(f"设置帧率失败: {e}")
            return False
    
    def set_exposure(self, exposure_us: int) -> bool:
        """设置曝光时间"""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return False
        
        try:
            self.camera.set_controls({"ExposureTime": exposure_us})
            self.exposure_us = exposure_us
            logger.info(f"曝光时间设置为: {exposure_us}μs")
            return True
        except Exception as e:
            logger.error(f"设置曝光时间失败: {e}")
            return False
    
    def set_gain(self, analogue_gain: float, digital_gain: float = 1.0) -> bool:
        """设置增益"""
        if not self.is_initialized:
            logger.error("相机未初始化")
            return False
        
        try:
            # 优先同时设置，若不支持 DigitalGain 则退化仅设置 AnalogueGain
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
            logger.info(f"增益设置为: 模拟={analogue_gain}, 数字={digital_gain}")
            return True
        except Exception as e:
            logger.error(f"设置增益失败: {e}")
            return False
    
    def set_rotation(self, rotation: int) -> bool:
        """设置图像旋转角度"""
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
                # native/crop 下输出与采集一致
                self.capture_width = self.width
                self.capture_height = self.height
                self.output_width = self.width
                self.output_height = self.height
                logger.info(f"非超采样模式，捕获和输出分辨率设置为: {self.output_width}x{self.output_height}")
            else:
                # 超采样模式：设置更高的捕获分辨率
                self.output_width = self.width
                self.output_height = self.height
                # 设置捕获分辨率为更高的分辨率
                self.capture_width = max(self.width * 2, 1280)
                self.capture_height = max(self.height * 2, 720)
                self._adjust_capture_resolution_to_aspect_ratio()
                
                # 记录详细配置信息
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
        """获取相机信息"""
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
            }
        except Exception as e:
            logger.error(f"获取相机信息失败: {e}")
            return {}


class CameraFactory:
    """相机工厂类"""
    
    @staticmethod
    def create_camera(camera_type: str, config: Dict[str, Any]) -> Optional[CameraInterface]:
        """创建相机实例"""
        if camera_type == "imx327_mipi":
            return IMX327MIPICamera(config)
        else:
            logger.error(f"不支持的相机类型: {camera_type}")
            return None


# 兼容性函数，用于平滑迁移
def create_camera(config: Dict[str, Any]) -> Optional[CameraInterface]:
    """创建相机的便捷函数"""
    camera_type = config.get("type", "imx327_mipi")
    return CameraFactory.create_camera(camera_type, config)
