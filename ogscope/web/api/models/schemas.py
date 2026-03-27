"""
API 数据模型定义
"""
from pydantic import BaseModel
from typing import Optional, Dict, Any


class CameraSettings(BaseModel):
    """相机设置 / camera settings"""
    exposure: int  # 曝光时间 (微秒) / Exposure time (microseconds)
    gain: float    # 增益 / Gain
    autoExposure: Optional[bool] = True  # 自动曝光开关 / automatic exposure switch
    digitalGain: Optional[float] = 1.0  # 数字增益 / digital gain
    contrast: Optional[float] = 1.0     # 对比度 / Contrast
    brightness: Optional[float] = 0.0   # 亮度 / brightness
    saturation: Optional[float] = 1.0   # 饱和度 / saturation
    sharpness: Optional[float] = 1.0    # 锐度 / sharpness
    noiseReduction: Optional[int] = 0   # 降噪级别 (0-4) / Noise reduction level (0-4)
    whiteBalanceMode: Optional[str] = 'auto'  # 白平衡模式 / white balance mode
    whiteBalanceGainR: Optional[float] = 1.0  # 白平衡红色增益 / white balance red gain
    whiteBalanceGainB: Optional[float] = 1.0  # 白平衡蓝色增益 / white balance blue gain
    colorMode: Optional[str] = 'color'  # 颜色模式: 'color' | 'mono'


class CameraPreset(BaseModel):
    """相机预设 / camera presets"""
    name: str
    description: str = ""
    exposure_us: int
    analogue_gain: float
    digital_gain: float = 1.0
    auto_exposure: bool = False
    auto_gain: bool = False
    # 图像增强参数 / Image enhancement parameters
    contrast: Optional[float] = 1.0
    brightness: Optional[float] = 0.0
    saturation: Optional[float] = 1.0
    sharpness: Optional[float] = 1.0
    # 高级参数 / Advanced parameters
    noise_reduction: Optional[int] = 0
    white_balance_mode: Optional[str] = 'auto'
    white_balance_gain_r: Optional[float] = 1.0
    white_balance_gain_b: Optional[float] = 1.0
    # 其他参数 / Other parameters
    rotation: Optional[int] = 180
    color_mode: Optional[str] = 'color'  # 颜色模式: 'color' | 'mono'


class CaptureInfo(BaseModel):
    """拍摄信息 / Shooting information"""
    filename: str
    timestamp: str
    exposure_us: int
    analogue_gain: float
    digital_gain: float
    resolution: str
    file_size: int


class SystemInfo(BaseModel):
    """系统信息 / System information"""
    platform: str
    os: str
    cpu_usage: float
    memory_usage: float
    temperature: float


class AlignmentStatus(BaseModel):
    """校准状态 / calibration status"""
    status: str
    azimuth_error: float
    altitude_error: float
    precision: str
    progress: int
