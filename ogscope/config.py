"""
配置管理模块
"""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置 / Application configuration"""

    # 基础配置 / Basic configuration
    environment: str = Field(default="development", description="运行环境")
    debug: bool = Field(default=True, description="调试模式")

    # Web 服务配置 / Web service configuration
    host: str = Field(default="0.0.0.0", description="Web 服务地址")
    port: int = Field(default=8000, description="Web 服务端口")
    reload: bool = Field(default=True, description="代码变更时自动重载")

    # 日志配置 / Log configuration
    log_level: str = Field(default="INFO", description="日志级别")
    log_file: Optional[Path] = Field(default=None, description="日志文件路径")

    # 相机配置 / Camera configuration
    camera_type: str = Field(default="imx327_mipi", description="相机类型: usb/csi/spi")
    camera_width: int = Field(
        default=1600, description="图像宽度 / Default capture width"
    )
    camera_height: int = Field(
        default=900, description="图像高度 / Default capture height"
    )
    camera_fps: int = Field(
        default=5, description="预览与调试默认帧率 / Default preview FPS"
    )
    camera_sampling_mode: str = Field(
        default="native", description="采样模式: supersample/native/crop"
    )
    camera_exposure: int = Field(default=10000, description="曝光时间(us)")
    camera_gain: float = Field(default=1.0, description="增益")

    # 显示屏配置 / Display configuration
    display_enabled: bool = Field(default=False, description="启用 SPI 屏幕")
    display_type: str = Field(default="st7789", description="显示屏类型")
    display_width: int = Field(default=240, description="屏幕宽度")
    display_height: int = Field(default=320, description="屏幕高度")
    display_rotation: int = Field(default=0, description="屏幕旋转角度")

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
    template_dir: Path = Field(default=Path("./web/templates"), description="模板目录")

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
        default=1600,
        description="提星前长边上限（像素），与默认采集长边对齐 / Max long side before extraction",
    )
    solver_large_scale_bg_downsample: int = Field(
        default=256,
        ge=32,
        le=2048,
        description="大尺度背景减除：小图长边上限（像素），越小越快 / Large-scale BG downsample max side",
    )
    star_analysis_target_fps: float = Field(
        default=2 / 3,
        description="星空分析目标帧率（约 1.5 秒 1 帧），仅用于前端节流 / Target star-analysis FPS for UI throttle (~1.5s per frame)",
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
    wifi_emergency_gpio_enabled: bool = Field(
        default=False,
        description="启用短接 GPIO 强制切 STA / Enable GPIO short-to-STA recovery",
    )
    wifi_emergency_pin_out_bcm: int = Field(
        default=22,
        description="应急检测：输出低电平（BCM）/ Emergency: output LOW (BCM)",
    )
    wifi_emergency_pin_in_bcm: int = Field(
        default=23,
        description="应急检测：上拉输入（BCM）/ Emergency: input with pull-up (BCM)",
    )
    wifi_emergency_hold_seconds: float = Field(
        default=2.0,
        ge=0.5,
        le=30.0,
        description="短接持续多久触发 STA / Hold time before forcing STA",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="OGSCOPE_",
        case_sensitive=False,
    )

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
