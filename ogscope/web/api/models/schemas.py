"""
API 数据模型定义
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CameraSettings(BaseModel):
    """相机设置 / camera settings"""

    exposure: int  # 曝光时间 (微秒) / Exposure time (microseconds)
    gain: float  # 增益 / Gain
    autoExposure: Optional[bool] = True  # 自动曝光开关 / automatic exposure switch
    digitalGain: Optional[float] = 1.0  # 数字增益 / digital gain
    contrast: Optional[float] = 1.0  # 对比度 / Contrast
    brightness: Optional[float] = 0.0  # 亮度 / brightness
    saturation: Optional[float] = 1.0  # 饱和度 / saturation
    sharpness: Optional[float] = 1.0  # 锐度 / sharpness
    noiseReduction: Optional[int] = 0  # 降噪级别 (0-4) / Noise reduction level (0-4)
    whiteBalanceMode: Optional[str] = "auto"  # 白平衡模式 / white balance mode
    whiteBalanceGainR: Optional[float] = 1.0  # 白平衡红色增益 / white balance red gain
    whiteBalanceGainB: Optional[float] = 1.0  # 白平衡蓝色增益 / white balance blue gain
    colorMode: Optional[str] = "color"  # 颜色模式: 'color' | 'mono'


class CameraMirrorBody(BaseModel):
    """相机输出镜像（与解算同坐标系）/ Camera output mirror (same frame as plate solve)"""

    flip_horizontal: bool = False
    flip_vertical: bool = False


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
    white_balance_mode: Optional[str] = "auto"
    white_balance_gain_r: Optional[float] = 1.0
    white_balance_gain_b: Optional[float] = 1.0
    # 其他参数 / Other parameters
    rotation: Optional[int] = 180
    flip_horizontal: Optional[bool] = False
    flip_vertical: Optional[bool] = False
    color_mode: Optional[str] = "color"  # 颜色模式: 'color' | 'mono'


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


class WifiStatus(BaseModel):
    """WiFi 模式状态 / WiFi mode status (STA vs AP)."""

    mode: Literal["ap", "sta", "unknown"]
    active_connection: Optional[str] = None
    wireless_interface: str = "wlan0"
    sta_connection: str = ""
    ap_connection: str = ""
    ap_ipv4: Optional[str] = None
    ap_url_hint: Optional[str] = None
    configured: bool = True
    message: Optional[str] = None
    device_id_suffix: Optional[str] = None
    ap_ssid: Optional[str] = None
    mdns_hostname_hint: Optional[str] = None


class WifiModeRequest(BaseModel):
    """切换 WiFi 模式 / Switch WiFi mode."""

    mode: Literal["ap", "sta"]


class WifiNetworkScanEntry(BaseModel):
    """扫描到的 WiFi / One scanned WiFi network."""

    ssid: str
    signal: Optional[int] = None
    security: Optional[str] = None


class WifiScanResponse(BaseModel):
    """WiFi 扫描结果 / WiFi scan response."""

    networks: list[WifiNetworkScanEntry]
    hint: Optional[str] = Field(
        default=None,
        description="空列表或降级时的说明（如 AP 模式无法扫描）/ UX hint when empty or degraded",
    )


class WifiProfileEntry(BaseModel):
    """已保存的 WiFi 连接 / Saved WiFi connection profile."""

    connection_name: str
    ssid: str
    autoconnect: bool


class WifiProfilesResponse(BaseModel):
    """已保存配置列表 / Saved profiles list."""

    profiles: list[WifiProfileEntry]


class WifiStaConnectRequest(BaseModel):
    """连接外部 WiFi（切 STA）/ Connect to external WiFi (STA mode)."""

    ssid: str
    password: Optional[str] = None


class WifiProfileActivateRequest(BaseModel):
    """激活已保存连接 / Activate saved connection."""

    connection_name: str


class AlignmentStatus(BaseModel):
    """校准状态 / calibration status"""

    status: str
    azimuth_error: float
    altitude_error: float
    precision: str
    progress: int


class CentroidParamsPayload(BaseModel):
    """Tetra3 提星参数覆盖（未填则用环境默认）/ Optional centroid extraction overrides."""

    model_config = ConfigDict(extra="forbid")

    sigma: Optional[float] = None
    max_area: Optional[int] = None
    min_area: Optional[int] = None
    filtsize: Optional[int] = None
    binary_open: Optional[bool] = None
    bg_sub_mode: Optional[str] = None
    sigma_mode: Optional[str] = None
    max_axis_ratio: Optional[float] = None

    @field_validator("filtsize")
    @classmethod
    def filtsize_must_be_odd(cls, v: Optional[int]) -> Optional[int]:
        """滤波边长须为奇数 / Filter size must be odd (Tetra3)."""
        if v is None:
            return None
        if v < 1:
            raise ValueError("filtsize must be >= 1")
        if v % 2 == 0:
            raise ValueError("filtsize must be odd")
        return v


class AnalysisSolveImageRequest(BaseModel):
    """单图解算请求（JSON body）/ Single-image plate solve request."""

    model_config = ConfigDict(extra="forbid")

    input_name: str
    hint_ra_deg: Optional[float] = None
    hint_dec_deg: Optional[float] = None
    fov_estimate: Optional[float] = None
    fov_max_error: Optional[float] = None
    solve_timeout_ms: Optional[int] = None
    solve_profile: Optional[Literal["speed", "balanced", "robust"]] = None
    centroid: Optional[CentroidParamsPayload] = None
    max_image_side: Optional[int] = None
    large_scale_bg_subtract: Optional[bool] = False
    # 结果详细程度：summary 仅返回关键字段，full 包含 tetra 原始块 / Result detail level
    detail_level: Optional[Literal["summary", "full"]] = "summary"
    # 质心几何剔除强度 1–5（过密/共线）；默认 3 / Centroid rejection strength
    centroid_rejection_level: Optional[int] = Field(
        default=3,
        ge=1,
        le=5,
        description="1=mild … 5=aggressive dense+collinear rejection",
    )


class AnalysisExtractPreviewRequest(BaseModel):
    """提星掩膜预览请求 / Centroid extraction preview (binary mask)."""

    model_config = ConfigDict(extra="forbid")

    input_name: str
    centroid: Optional[CentroidParamsPayload] = None
    max_image_side: Optional[int] = None
    large_scale_bg_subtract: Optional[bool] = False


class AnalysisJobCreateRequest(BaseModel):
    """分析任务创建请求 / Analysis job create request"""

    input_name: str
    input_type: str  # image | video
    hint_ra_deg: Optional[float] = None
    hint_dec_deg: Optional[float] = None
    frame_step: int = 1
    max_frames: int = 180
    fov_estimate: Optional[float] = None
    fov_max_error: Optional[float] = None
    solve_timeout_ms: Optional[int] = None
    centroid: Optional[CentroidParamsPayload] = None
    max_image_side: Optional[int] = None
    large_scale_bg_subtract: Optional[bool] = False
    centroid_rejection_level: Optional[int] = Field(
        default=3,
        ge=1,
        le=5,
    )


class SolveFrameResult(BaseModel):
    """单帧解算结果 / Single frame solving result"""

    frame_index: int
    ra_deg: float
    dec_deg: float
    solve_source: str
    status: str = ""


class AnalysisJobStatusResponse(BaseModel):
    """分析任务状态响应 / Analysis job status response"""

    job_id: str
    status: str
    progress: float
    message: str = ""
    result_path: Optional[str] = None


class AnalysisSolveParamsOnly(BaseModel):
    """解算参数（不含文件名，用于预设与批量）/ Solve params without input filename."""

    model_config = ConfigDict(extra="forbid")

    hint_ra_deg: Optional[float] = None
    hint_dec_deg: Optional[float] = None
    fov_estimate: Optional[float] = None
    fov_max_error: Optional[float] = None
    solve_timeout_ms: Optional[int] = None
    solve_profile: Optional[Literal["speed", "balanced", "robust"]] = None
    centroid: Optional[CentroidParamsPayload] = None
    max_image_side: Optional[int] = None
    large_scale_bg_subtract: Optional[bool] = False
    detail_level: Optional[Literal["summary", "full"]] = "summary"
    centroid_rejection_level: Optional[int] = Field(
        default=3,
        ge=1,
        le=5,
    )


class BatchSolveRunItem(BaseModel):
    """批量解算单轮 / One batch solve run."""

    label: str
    params: AnalysisSolveParamsOnly


class AnalysisBatchSolveRequest(BaseModel):
    """批量解算请求 / Batch plate solve request."""

    model_config = ConfigDict(extra="forbid")

    input_name: str
    runs: list[BatchSolveRunItem]


class AnalysisPresetCreate(BaseModel):
    """用户预设创建 / User preset create."""

    model_config = ConfigDict(extra="forbid")

    name: str
    params: AnalysisSolveParamsOnly


class AnalysisExperimentCreate(BaseModel):
    """实验记录保存 / Save experiment record."""

    model_config = ConfigDict(extra="forbid")

    input_name: str
    preset_label: str
    result_json: dict[str, Any]
    metrics: dict[str, Any] = Field(default_factory=dict)
    thumbnail_png_base64: Optional[str] = None
    replay: Optional[dict[str, Any]] = None
    save_asset_snapshot: bool = True


class AnalysisSolveVideoFrameRequest(BaseModel):
    """单帧解算：相机 BGR 或素材池视频 seek / Solve one frame from camera or pool video."""

    model_config = ConfigDict(extra="forbid")

    # 基本输入来源 / Basic input source
    source: Literal["camera", "file"]
    input_name: Optional[str] = None
    frame_index: int = 0
    time_sec: Optional[float] = None
    solve_interval_ms: Optional[int] = Field(
        default=None,
        ge=200,
        le=60000,
        description="期望解算间隔（毫秒）；后端会按系统上下限裁剪 / Desired solve interval in ms (server-clamped)",
    )
    # 解算参数 / Solve parameters
    hint_ra_deg: Optional[float] = None
    hint_dec_deg: Optional[float] = None
    fov_estimate: Optional[float] = None
    fov_max_error: Optional[float] = None
    solve_timeout_ms: Optional[int] = None
    solve_profile: Optional[Literal["speed", "balanced", "robust"]] = None
    centroid: Optional[CentroidParamsPayload] = None
    max_image_side: Optional[int] = None
    large_scale_bg_subtract: Optional[bool] = False
    detail_level: Optional[Literal["summary", "full"]] = "summary"

    # 叠加与引导选项（可选，未提供则使用后端默认）/ Optional overlay & guidance options
    overlay_topn_count: Optional[int] = Field(
        default=None,
        description="自动标注的星点数量上限（Top-N），未填用服务器默认 / Max number of stars to label (Top-N); server default if omitted",
    )
    enable_polar_guide: Optional[bool] = Field(
        default=None,
        description="是否计算极轴引导信息；未填用服务器默认 / Whether to compute polar guide info; server default if omitted",
    )
    centroid_rejection_level: Optional[int] = Field(
        default=3,
        ge=1,
        le=5,
        description="质心几何剔除档位 / Centroid rejection level",
    )


class ImportFromDebugRequest(BaseModel):
    """从调试采集目录导入到分析素材池 / Import capture into analysis pool."""

    model_config = ConfigDict(extra="forbid")

    filename: str


class AnalysisReplaceVideoRequest(BaseModel):
    """转码后替换素材视频 / Replace original video after client transcode."""

    model_config = ConfigDict(extra="forbid")

    old_filename: str
    new_filename: str
    duration_s: Optional[float] = None
    nominal_fps: Optional[float] = None
    codec_fourcc: Optional[str] = None
    container: Optional[str] = None
