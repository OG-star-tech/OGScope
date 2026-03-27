"""
API 数据模型定义
"""
from pydantic import BaseModel
from typing import Optional, Dict, Any


class CameraSettings(BaseModel):
    """相机设置"""
    exposure: int  # 曝光时间 (微秒)
    gain: float    # 增益
    autoExposure: Optional[bool] = True  # 自动曝光开关
    digitalGain: Optional[float] = 1.0  # 数字增益
    contrast: Optional[float] = 1.0     # 对比度
    brightness: Optional[float] = 0.0   # 亮度
    saturation: Optional[float] = 1.0   # 饱和度
    sharpness: Optional[float] = 1.0    # 锐度
    noiseReduction: Optional[int] = 0   # 降噪级别 (0-4)
    whiteBalanceMode: Optional[str] = 'auto'  # 白平衡模式
    whiteBalanceGainR: Optional[float] = 1.0  # 白平衡红色增益
    whiteBalanceGainB: Optional[float] = 1.0  # 白平衡蓝色增益
    colorMode: Optional[str] = 'color'  # 颜色模式: 'color' | 'mono'


class PolarAlignStatus(BaseModel):
    """极轴校准状态"""
    is_running: bool
    progress: float  # 0-100
    azimuth_error: float  # 方位误差 (角分)
    altitude_error: float  # 高度误差 (角分)


class CameraPreset(BaseModel):
    """相机预设"""
    name: str
    description: str = ""
    exposure_us: int
    analogue_gain: float
    digital_gain: float = 1.0
    auto_exposure: bool = False
    auto_gain: bool = False
    # 图像增强参数
    contrast: Optional[float] = 1.0
    brightness: Optional[float] = 0.0
    saturation: Optional[float] = 1.0
    sharpness: Optional[float] = 1.0
    # 高级参数
    noise_reduction: Optional[int] = 0
    white_balance_mode: Optional[str] = 'auto'
    white_balance_gain_r: Optional[float] = 1.0
    white_balance_gain_b: Optional[float] = 1.0
    # 其他参数
    rotation: Optional[int] = 180
    color_mode: Optional[str] = 'color'  # 颜色模式: 'color' | 'mono'


class CaptureInfo(BaseModel):
    """拍摄信息"""
    filename: str
    timestamp: str
    exposure_us: int
    analogue_gain: float
    digital_gain: float
    resolution: str
    file_size: int


class SystemInfo(BaseModel):
    """系统信息"""
    platform: str
    os: str
    cpu_usage: float
    memory_usage: float
    temperature: float


class AlignmentStatus(BaseModel):
    """校准状态"""
    status: str
    azimuth_error: float
    altitude_error: float
    precision: str
    progress: int
