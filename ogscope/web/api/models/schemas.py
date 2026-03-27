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
    wifi_quality: Optional[float] = None
    wifi_signal_dbm: Optional[float] = None
    wifi_interface: Optional[str] = None
    uptime_seconds: int = 0
    load_average_1m: float = 0.0


class AlignmentStatus(BaseModel):
    """校准状态 / calibration status"""
    status: str
    azimuth_error: float
    altitude_error: float
    precision: str
    progress: int


class CatalogDownloadRequest(BaseModel):
    """星表下载请求 / Catalog download request"""

    source: str = "seed"
    url: Optional[str] = None
    magnitude_limit: float = 8.5


class CatalogBuildIndexRequest(BaseModel):
    """星表索引构建请求 / Catalog build index request"""

    magnitude_limit: float = 8.5
    ra_bin_size_deg: float = 15.0


class CatalogStarUpsertRequest(BaseModel):
    """星点新增/更新请求 / Catalog star upsert request"""

    source_id: str
    ra: float
    dec: float
    pmra: float = 0.0
    pmdec: float = 0.0
    phot_g_mean_mag: float
    name_en: Optional[str] = None
    name_zh: Optional[str] = None
    description_en: Optional[str] = None
    description_zh: Optional[str] = None


class AnalysisJobCreateRequest(BaseModel):
    """分析任务创建请求 / Analysis job create request"""

    input_name: str
    input_type: str  # image | video
    hint_ra_deg: Optional[float] = None
    hint_dec_deg: Optional[float] = None
    frame_step: int = 1
    max_frames: int = 180


class SolveFrameResult(BaseModel):
    """单帧解算结果 / Single frame solving result"""

    frame_index: int
    ra_deg: float
    dec_deg: float
    confidence: float
    solve_source: str


class AnalysisJobStatusResponse(BaseModel):
    """分析任务状态响应 / Analysis job status response"""

    job_id: str
    status: str
    progress: float
    message: str = ""
    result_path: Optional[str] = None
