"""
API 数据模型定义
"""
from pydantic import BaseModel
from typing import Optional, Dict, Any


class CameraSettings(BaseModel):
    """相机设置"""
    exposure: int  # 曝光时间 (微秒)
    gain: float    # 增益


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
