"""
配置管理模块
"""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置 / Application configuration"""

    # 基础配置 / Basic configuration
    environment: str = Field(default="development", description="运行环境")
    debug: bool = Field(default=True, description="调试模式")
    development_mode: bool = Field(
        default=False,
        description=(
            "开发模式：更详细日志与更完整异常栈（部署时谨慎开启）/ "
            "Development mode: richer logs and fuller exception traces (use carefully in prod)"
        ),
    )

    # Web 服务配置 / Web service configuration
    host: str = Field(default="0.0.0.0", description="Web 服务地址")
    port: int = Field(default=8000, description="Web 服务端口")
    reload: bool = Field(default=True, description="代码变更时自动重载")

    # 硬件平面配置 / Hardware plane configuration
    hardware_plane_enabled: bool = Field(
        default=True,
        description="启用共享硬件平面 / Enable shared hardware plane",
    )
    hardware_plane_role: str = Field(
        default="standalone",
        description=(
            "硬件平面角色：standalone 或 subordinate / "
            "Hardware plane role: standalone or subordinate"
        ),
    )
    hardware_plane_rpc_timeout_ms: int = Field(
        default=800,
        ge=50,
        le=10000,
        description="硬件平面 RPC 超时（毫秒）/ Hardware plane RPC timeout in ms",
    )
    hardware_plane_uds_socket: Path = Field(
        default=Path("/tmp/ogscope-hardware-plane.sock"),
        description="硬件平面 UDS 套接字路径 / Hardware plane UDS socket path",
    )
    hardware_plane_remote_uds_socket: Path = Field(
        default=Path("/tmp/external-sensor-plane.sock"),
        description=(
            "外部传感器 UDS 套接字路径（仅 subordinate 使用） / "
            "External sensor UDS socket path (used in subordinate mode)"
        ),
    )
    hardware_plane_camera_autostart: bool = Field(
        default=False,
        description="开机阶段自动启动相机服务 / Auto-start camera service during boot phases",
    )
    enable_local_sensors: bool = Field(
        default=True,
        description="启用 OGScope 本地传感器服务 / Enable OGScope local sensor services",
    )
    enable_hmi: bool = Field(
        default=True,
        description="启用 OGScope HMI 服务 / Enable OGScope HMI services",
    )
    enable_ui: bool = Field(
        default=True,
        description="启用 OGScope 用户界面路由 / Enable OGScope UI routes",
    )
    subordinate_local_dev_only: bool = Field(
        default=False,
        description=(
            "在 subordinate 角色下，仅允许本机访问 /api/dev/*（联调用途） / "
            "In subordinate role, allow /api/dev/* only from localhost for integration"
        ),
    )

    # 日志配置 / Log configuration
    log_level: str = Field(default="INFO", description="日志级别")
    log_file: Optional[Path] = Field(default=None, description="日志文件路径")

    # 相机配置 / Camera configuration
    camera_type: str = Field(default="imx327_mipi", description="相机类型: usb/csi/spi")
    camera_width: int = Field(
        default=1280, description="图像宽度 / Default capture width"
    )
    camera_height: int = Field(
        default=720, description="图像高度 / Default capture height"
    )
    camera_fps: int = Field(
        default=8, description="传感器目标帧率 / Target sensor FPS"
    )
    camera_sampling_mode: str = Field(
        default="native", description="采样模式: supersample/native/crop"
    )
    camera_exposure: int = Field(default=10000, description="曝光时间(us)")
    camera_gain: float = Field(default=1.0, description="增益")
    camera_ae_polar_preset: bool = Field(
        default=True,
        description="自动曝光时启用电子极轴镜 AE 预设 (Shadows/Matrix/Long+EV) / AE polar-scope preset",
    )
    camera_ae_exposure_value: float = Field(
        default=0.35,
        ge=-2.0,
        le=2.0,
        description="AE 曝光补偿(档)，与 camera_ae_polar_preset 联用 / AE exposure comp EV stops",
    )
    camera_auto_exposure_max_us: int = Field(
        default=2_000_000,
        ge=10_000,
        le=10_000_000,
        description="自动曝光最长帧周期 us，暗场允许降帧 / Max auto-exposure frame duration in us",
    )
    camera_ae_flicker_mode: str = Field(
        default="off",
        description="AE 防闪烁模式 off/50hz/60hz / AE flicker mode: off/50hz/60hz",
    )
    camera_noise_reduction_mode: str = Field(
        default="fast",
        description="降噪语义模式 off/fast/high_quality / Semantic noise reduction mode",
    )
    camera_lores_enabled: bool = Field(
        default=True,
        description="启用低分辨率辅助流用于统计 / Enable lores helper stream for stats",
    )
    camera_lores_width: int = Field(
        default=320,
        ge=64,
        le=1280,
        description="低分辨率辅助流宽度 / Lores helper stream width",
    )
    camera_lores_height: int = Field(
        default=240,
        ge=48,
        le=720,
        description="低分辨率辅助流高度 / Lores helper stream height",
    )
    camera_lores_format: str = Field(
        default="YUV420",
        description="低分辨率辅助流格式 / Lores helper stream format",
    )
    camera_flip_horizontal: bool = Field(
        default=False,
        description="相机输出水平镜像；与预览/解算同坐标系 / Camera output horizontal flip",
    )
    camera_flip_vertical: bool = Field(
        default=False,
        description="相机输出垂直镜像；与预览/解算同坐标系 / Camera output vertical flip",
    )
    camera_white_balance_mode: str = Field(
        default="auto",
        description="白平衡模式 auto/manual/night / White balance mode: auto/manual/night",
    )
    camera_white_balance_gain_r: float = Field(
        default=1.0,
        ge=0.1,
        le=3.0,
        description="手动白平衡红色增益 / Manual white-balance red gain",
    )
    camera_white_balance_gain_b: float = Field(
        default=1.0,
        ge=0.1,
        le=3.0,
        description="手动白平衡蓝色增益 / Manual white-balance blue gain",
    )
    camera_night_mode: bool = Field(
        default=False,
        description="启动时应用夜间白平衡标记 / Apply night white-balance mode on startup",
    )

    # 显示屏配置 / Display configuration
    display_enabled: bool = Field(default=False, description="启用 SPI 屏幕")
    display_type: str = Field(default="st7796", description="显示屏类型（如 st7796）")
    display_width: int = Field(default=320, description="屏幕宽度")
    display_height: int = Field(default=320, description="屏幕高度")
    display_rotation: int = Field(default=0, description="屏幕旋转角度")
    display_dc_pin: int = Field(
        default=24,
        ge=2,
        le=40,
        description="SPI DC 引脚（BCM）/ SPI DC GPIO (BCM)",
    )
    display_spi_max_speed_hz: int = Field(
        default=16_000_000,
        ge=500_000,
        le=62_000_000,
        description="SPI 屏幕总线最高速率 Hz / SPI bus max Hz for LCD",
    )

    # 极轴校准配置 / Polar calibration configuration
    polar_align_timeout: int = Field(default=300, description="校准超时时间(秒)")
    polar_align_precision: float = Field(default=1.0, description="校准精度(角分)")

    # 数据库配置 / Database configuration
    database_url: str = Field(
        default="sqlite:///./ogscope.db", description="数据库连接字符串"
    )

    # 文件路径配置 / File path configuration
    data_dir: Path = Field(default=Path("./data"), description="数据目录")
    upload_dir: Path = Field(default=Path("./uploads"), description="上传目录")
    analysis_dir: Path = Field(
        default=Path("./data/analysis"), description="分析任务目录"
    )
    plate_solve_dir: Path = Field(
        default=Path("./data/plate_solve"),
        description="Tetra3 图案库目录 / Tetra3 pattern database directory",
    )
    solver_tetra_database_path: Optional[Path] = Field(
        default=None,
        description="default_database.npz 绝对路径；None 则使用 vendor 内 data/default_database.npz / Absolute path to default_database.npz",
    )
    solver_fov_max_error_deg: Optional[float] = Field(
        default=None,
        description="FOV 估计允许误差(度)；None 为库默认 / Max FOV estimate error in degrees",
    )
    solver_timeout_ms: int = Field(
        default=1500,
        description="Tetra3 单次解算超时毫秒 / Tetra3 solve timeout in ms",
    )
    static_dir: Path = Field(default=Path("./web/static"), description="静态文件目录")

    # 星图解算配置 / Plate solving configuration
    solver_hint_ra_deg: float = Field(default=0.0, description="默认解算RA提示(度)")
    solver_hint_dec_deg: float = Field(default=90.0, description="默认解算Dec提示(度)")
    solver_fov_deg: float = Field(
        default=11.0, description="视场角(度) / Default FOV estimate (deg)"
    )
    solver_max_stars: int = Field(default=80, description="用于解算的最大星点数量")
    solver_fullsolve_interval_frames: int = Field(
        default=10, description="实时模式全量解算间隔帧数"
    )
    # Tetra3 get_centroids_from_image 默认（可环境覆盖）/ Defaults for centroid extraction
    solver_centroid_sigma: float = Field(
        default=2.5,
        description="σ 阈值倍数；略高可减少假星 / Sigma multiplier for thresholding",
    )
    solver_centroid_max_area: int = Field(
        default=400,
        description="连通域最大像素面积；过小会丢掉亮星光晕 / Max spot area in pixels",
    )
    solver_centroid_min_area: int = Field(
        default=5,
        description="连通域最小像素面积 / Min spot area in pixels",
    )
    solver_centroid_filtsize: int = Field(
        default=25,
        description="局部背景/噪声滤波边长，须为奇数 / Local filter size (odd)",
    )
    solver_centroid_binary_open: bool = Field(
        default=True,
        description="二值开运算去噪 / Binary opening on threshold mask",
    )
    solver_centroid_bg_sub_mode: str = Field(
        default="local_mean",
        description="背景扣除模式 / Background subtraction mode (Tetra3)",
    )
    solver_centroid_sigma_mode: str = Field(
        default="global_root_square",
        description="噪声 σ 估计模式 / Noise sigma mode (Tetra3)",
    )
    solver_centroid_max_axis_ratio: Optional[float] = Field(
        default=None,
        description="长细比上限；None 为不限制 / Max major/minor axis ratio, None to disable",
    )
    solver_max_image_side: int = Field(
        default=1280,
        description="提星前长边上限（像素），与默认采集长边对齐 / Max long side before extraction",
    )
    solver_max_stars_hard_cap: Optional[int] = Field(
        default=None,
        ge=4,
        le=200,
        description=(
            "硬上限：所有解算路径的 max_stars（含 speed/balanced/robust 分档）不超过该值；"
            "None 表示不额外限制 / Hard cap on max stars for all solve paths; None disables"
        ),
    )
    solver_max_image_side_hard_cap: Optional[int] = Field(
        default=None,
        ge=256,
        le=4096,
        description=(
            "硬上限：提星前长边不超过该像素；None 表示不额外限制 / Hard cap on max image side; None disables"
        ),
    )
    solver_large_scale_bg_downsample: int = Field(
        default=256,
        ge=32,
        le=2048,
        description="大尺度背景减除：小图长边上限（像素），越小越快 / Large-scale BG downsample max side",
    )
    star_analysis_target_fps: float = Field(
        default=0.5,
        description="星空分析目标帧率（默认 2 秒 1 帧）/ Target star-analysis FPS (one frame per 2 seconds)",
    )
    star_analysis_min_interval_ms: int = Field(
        default=2000,
        ge=500,
        le=30000,
        description="实时解算最小间隔（毫秒）/ Minimum interval for realtime solving in ms",
    )
    star_analysis_max_interval_ms: int = Field(
        default=12000,
        ge=1000,
        le=60000,
        description="实时解算最大间隔（毫秒）/ Maximum interval for realtime solving in ms",
    )
    star_analysis_request_timeout_ms: int = Field(
        default=4500,
        ge=500,
        le=120000,
        description="实时解算请求外层硬超时（毫秒）/ Outer hard timeout for realtime solve request in ms",
    )
    star_analysis_slow_threshold_ms: int = Field(
        default=3000,
        ge=200,
        le=120000,
        description="实时解算慢请求阈值（毫秒）/ Slow realtime solve threshold in ms",
    )
    stream_max_mjpeg_clients: int = Field(
        default=4,
        ge=0,
        le=32,
        description=(
            "同时允许的 MJPEG 长连接数（GET /api/dev/debug/camera/stream）；"
            "默认 4 以容纳多标签页与短暂重叠；0=不限制 / "
            "Max concurrent MJPEG streams; default 4 for multi-tab overlap; 0=unlimited"
        ),
    )
    stream_mjpeg_frame_fetch_timeout_ms: int = Field(
        default=20000,
        ge=3000,
        le=120000,
        description=(
            "MJPEG 循环单次取帧（含编码线程）最大等待毫秒；超时则结束流并释放名额，"
            "避免异常断开时长时间占满并发 / Max wait per MJPEG frame fetch (incl. encode thread); "
            "on timeout the stream ends to free slots after abnormal client disconnect"
        ),
    )

    # 预览与抓帧运行时 / Preview and shared grabber runtime
    shared_preview_fps: int = Field(
        default=8,
        ge=1,
        le=60,
        description="共享预览/MJPEG 目标帧率 / Target FPS for shared preview and MJPEG",
    )
    preview_jpeg_quality: int = Field(
        default=65,
        ge=1,
        le=100,
        description="共享抓帧 JPEG 质量 / JPEG quality for shared frame grabber",
    )
    preview_encoder: str = Field(
        default="auto",
        description="预览编码器 auto/turbojpeg/opencv / Preview encoder: auto/turbojpeg/opencv",
    )
    debug_preview_min_interval_ms: int = Field(
        default=150,
        ge=0,
        le=60000,
        description=(
            "调试预览 API 最小间隔（毫秒）；0=不限 / Min interval for debug preview API in ms; 0=unlimited"
        ),
    )
    camera_probe_timeout_sec: float = Field(
        default=2.0,
        ge=0.5,
        le=30.0,
        description="相机探测超时（秒）/ Camera probe timeout in seconds",
    )
    camera_grab_failures_offline: int = Field(
        default=3,
        ge=1,
        le=20,
        description=(
            "连续抓帧失败多少次后标记离线 / Consecutive grab failures before marking offline"
        ),
    )
    camera_idle_shutdown_sec: float = Field(
        default=20.0,
        ge=0.0,
        le=300.0,
        description="无消费者后相机热驻留秒数 / Camera warm-idle timeout after the last consumer",
    )
    camera_frame_stale_timeout_sec: float = Field(
        default=5.0,
        ge=0.5,
        le=60.0,
        description="超过该时间无成功帧时重新探测 / Re-probe after no successful frame for this duration",
    )
    keep_raw_cache: bool = Field(
        default=False,
        description=(
            "是否常驻 raw 帧缓存（占内存）；分析路径可同步抓帧 / "
            "Retain raw frame cache in RAM; analysis can sync-grab when false"
        ),
    )

    # 运行时行为 / Runtime behavior
    simulation_mode: Optional[bool] = Field(
        default=None,
        description=(
            "模拟模式：None=自动（非树莓派启用）；true/false 强制开关 / "
            "Simulation mode: None=auto (off on Pi); true/false to force"
        ),
    )
    force_exit_on_shutdown: bool = Field(
        default=True,
        description=(
            "CLI 退出时使用 os._exit，避免硬件线程阻塞进程退出 / "
            "Use os._exit on CLI shutdown to avoid hung hardware threads"
        ),
    )

    # WiFi（nmcli + scripts/ogscope-wifi-switch.sh）/ WiFi (NetworkManager helper script)
    wifi_switch_script: Path = Field(
        default=Path("/usr/local/bin/ogscope-wifi-switch"),
        description="WiFi 切换脚本路径 / Path to ogscope-wifi-switch script",
    )
    wifi_switch_use_sudo: bool = Field(
        default=True,
        description="调用脚本时是否使用 sudo -n / sudo -n when invoking script",
    )
    wifi_switch_timeout_seconds: int = Field(
        default=90,
        ge=10,
        le=600,
        description="nmcli 切换超时（秒）/ Timeout for nmcli switch",
    )
    wifi_nmcli_use_sudo: bool = Field(
        default=True,
        description=(
            "非 root 时对 nmcli 使用 sudo -n（需 sudoers 放行 nmcli；"
            "否则 polkit 会拒绝 connection up）/ sudo -n for nmcli when not root"
        ),
    )
    wifi_sta_connection: str = Field(
        default="",
        description="STA 模式 NM 连接名（空则禁用 WiFi API）/ STA connection name (empty disables API)",
    )
    wifi_ap_connection: str = Field(
        default="",
        description="AP 模式 NM 连接名 / AP connection name",
    )
    wifi_interface: str = Field(
        default="wlan0",
        description="无线接口名 / Wireless interface name",
    )
    wifi_ap_url_host: str = Field(
        default="192.168.4.1",
        description="AP 模式下前端提示用的主机地址（不含端口）/ AP URL hint host without port",
    )
    device_id_suffix: str = Field(
        default="",
        description="设备后缀（network.env 中 OGSCOPE_DEVICE_ID_SUFFIX）/ Device id suffix from network.env",
    )
    wifi_ap_ssid: str = Field(
        default="",
        description="AP 的 SSID（可选，来自 network.env）/ AP SSID from network.env",
    )
    wifi_sta_rollback_timeout_seconds: int = Field(
        default=90,
        ge=20,
        le=600,
        description="切 STA 后无可用 IPv4 则回滚 AP 的超时（秒）/ Roll back to AP if no IPv4",
    )
    wifi_sta_rollback_interval_seconds: int = Field(
        default=5,
        ge=2,
        le=60,
        description="STA 连通性轮询间隔（秒）/ Poll interval for STA rollback check",
    )

    model_config = SettingsConfigDict(
        env_file=(
            "/etc/ogscope/ogscope.env",
            "/etc/ogscope/network.env",
            ".env",
        ),
        env_file_encoding="utf-8",
        env_prefix="OGSCOPE_",
        case_sensitive=False,
    )

    @field_validator("simulation_mode", mode="before")
    @classmethod
    def _parse_simulation_mode(cls, value: object) -> Optional[bool]:
        """解析模拟模式三态（auto/true/false）/ Parse tri-state simulation mode."""
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"", "auto", "none", "default"}:
            return None
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
        return value  # type: ignore[return-value]

    @field_validator("camera_white_balance_mode", mode="before")
    @classmethod
    def _parse_camera_white_balance_mode(cls, value: object) -> str:
        """校验白平衡模式，非法值回退 auto / Validate WB mode and fall back to auto."""
        text = str(value or "auto").strip().lower()
        if text in {
            "auto",
            "daylight",
            "cloudy",
            "tungsten",
            "fluorescent",
            "indoor",
            "manual",
            "night",
        }:
            return text
        return "auto"

    @field_validator("camera_ae_flicker_mode", mode="before")
    @classmethod
    def _parse_camera_ae_flicker_mode(cls, value: object) -> str:
        """校验防闪烁模式 / Validate AE flicker mode."""
        text = str(value or "off").strip().lower().replace("_", "")
        if text in {"50", "50hz"}:
            return "50hz"
        if text in {"60", "60hz"}:
            return "60hz"
        return "off"

    @field_validator("camera_noise_reduction_mode", mode="before")
    @classmethod
    def _parse_camera_noise_reduction_mode(cls, value: object) -> str:
        """校验降噪语义模式 / Validate semantic noise reduction mode."""
        text = str(value or "fast").strip().lower().replace("-", "_")
        aliases = {"hq": "high_quality", "highquality": "high_quality", "0": "off"}
        text = aliases.get(text, text)
        if text in {"off", "fast", "high_quality"}:
            return text
        return "fast"

    @field_validator("preview_encoder", mode="before")
    @classmethod
    def _parse_preview_encoder(cls, value: object) -> str:
        """校验预览编码器偏好 / Validate preview encoder preference."""
        text = str(value or "auto").strip().lower()
        if text in {"auto", "turbojpeg", "opencv"}:
            return text
        return "auto"

    @model_validator(mode="after")
    def _apply_development_mode_defaults(self) -> "Settings":
        """开发模式默认提升日志级别（避免与显式 WARNING/ERROR 冲突）/ Dev mode bumps log level unless explicitly quiet."""
        if not bool(self.development_mode):
            return self
        if str(self.log_level).upper() == "INFO":
            object.__setattr__(self, "log_level", "DEBUG")
        return self

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 创建必要的目录 / Create necessary directories
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.analysis_dir.mkdir(parents=True, exist_ok=True)
        self.plate_solve_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """获取配置单例 / Get configuration singleton"""
    return Settings()


def effective_solver_max_stars(settings: Settings) -> int:
    """考虑 solver_max_stars_hard_cap 后的最大星点数 / Max stars after optional hard cap."""
    v = max(4, int(settings.solver_max_stars))
    cap = settings.solver_max_stars_hard_cap
    if cap is not None:
        v = min(v, int(cap))
    return v


def effective_solver_max_image_side(settings: Settings) -> int:
    """考虑 solver_max_image_side_hard_cap 后的提星长边 / Max image side after optional hard cap."""
    v = max(256, int(settings.solver_max_image_side))
    cap = settings.solver_max_image_side_hard_cap
    if cap is not None:
        v = min(v, int(cap))
    return v
