"""
配置管理模块
"""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ogscope.camera_optics import DEFAULT_EFFECTIVE_FOV_WIDTH_DEG


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
    camera_type: str = Field(
        default="imx327_mipi",
        description=(
            "相机后端：imx327_mipi（Picamera2/libcamera）或 v4l2 / "
            "Camera backend: imx327_mipi or v4l2"
        ),
    )
    camera_width: int = Field(
        default=1280, description="图像宽度 / Default capture width"
    )
    camera_height: int = Field(
        default=720, description="图像高度 / Default capture height"
    )
    camera_fps: int = Field(default=8, description="传感器目标帧率 / Target sensor FPS")
    camera_sampling_mode: str = Field(
        default="native", description="采样模式: supersample/native/crop"
    )
    camera_exposure: int = Field(default=10000, description="曝光时间(us)")
    camera_gain: float = Field(default=1.0, description="增益")
    camera_device: str = Field(
        default="/dev/video0", description="V4L2 视频设备 / V4L2 video device"
    )
    camera_v4l2_sensor_subdev: str = Field(
        default="/dev/v4l-subdev1",
        description="V4L2 传感器控制子设备 / V4L2 sensor control subdevice",
    )
    camera_v4l2_media_device: str = Field(
        default="/dev/media0",
        description="V4L2 Media Controller 设备 / V4L2 media-controller device",
    )
    camera_v4l2_configure_media_pipeline: bool = Field(
        default=True,
        description="启动时配置媒体链路 / Configure the media pipeline on startup",
    )
    camera_v4l2_sensor_entity: str = Field(
        default="imx327 10-001a",
        description="Media Controller 传感器实体 / Media-controller sensor entity",
    )
    camera_v4l2_receiver_entity: str = Field(
        default="unicam",
        description="Media Controller CSI 接收实体 / Media-controller CSI receiver entity",
    )
    camera_v4l2_sensor_pad: int = Field(
        default=0,
        ge=0,
        le=32,
        description="传感器源 pad 编号 / Sensor source-pad index",
    )
    camera_v4l2_receiver_sink_pad: int = Field(
        default=0,
        ge=-1,
        le=32,
        description=(
            "CSI 接收器 sink pad 编号，-1 跳过 / "
            "CSI receiver sink-pad index; -1 skips it"
        ),
    )
    camera_v4l2_receiver_source_pad: int = Field(
        default=1,
        ge=-1,
        le=32,
        description=(
            "CSI 接收器 source pad 编号，-1 跳过 / "
            "CSI receiver source-pad index; -1 skips it"
        ),
    )
    camera_v4l2_media_bus_format: str = Field(
        default="SRGGB10_1X10",
        description="传感器媒体总线格式 / Sensor media-bus format",
    )
    camera_v4l2_pixel_format: str = Field(
        default="RG10", description="V4L2 RAW 像素格式 / V4L2 RAW pixel format"
    )
    camera_v4l2_bit_depth: int = Field(
        default=10, ge=8, le=16, description="V4L2 RAW 位深 / V4L2 RAW bit depth"
    )
    camera_v4l2_black_level: int = Field(
        default=-1,
        ge=-1,
        le=65534,
        description="RAW 黑电平；-1 自动读取 / RAW black level; -1 auto-detects",
    )
    camera_v4l2_white_level: int = Field(
        default=0,
        ge=0,
        le=65535,
        description="RAW 白电平；0 自动推导 / RAW white level; 0 auto-detects",
    )
    camera_v4l2_bayer_pattern: str = Field(
        default="RGGB", description="V4L2 Bayer 排列 / V4L2 Bayer pattern"
    )
    camera_v4l2_gamma: float = Field(
        default=2.2,
        ge=1.0,
        le=4.0,
        description=(
            "RAW 路径去马赛克后的 gamma 校正，用于匹配 picamera2/libcamera "
            "ISP 色调曲线的对比度，使同一 solver_centroid_sigma 阈值在两条"
            "后端上可复用 / Gamma correction applied after RAW demosaic, "
            "matching picamera2/libcamera's ISP tone-curve contrast so the "
            "same solver_centroid_sigma threshold works on both backends"
        ),
    )
    camera_v4l2_temporal_nr_alpha: float = Field(
        default=0.2,
        ge=0.01,
        le=1.0,
        description=(
            "时域指数滑动平均降噪系数，1.0 关闭 / 不做累积：用真实静态场景连拍 "
            "10 帧、逐像素算跨帧标准差测出，V4L2（仅 gamma）的噪声是 "
            "picamera2 的 6.5 倍（3.55 对 0.55），因为这条路径完全没有降噪，"
            "picamera2 的 ISP 默认有。产品场景是静态/跟踪的星空，用时域累积而"
            "不是空间滤波，能在不牺牲空间分辨率的前提下压噪声。值越小压得越"
            "狠但响应越慢（收敛约需 1/alpha 帧）；曝光或增益一变就会清空累积"
            "器，不会把不同亮度的帧混在一起 / Temporal EMA noise-reduction "
            "coefficient; 1.0 disables it (no accumulation). Measured on real "
            "static-scene hardware (10-frame capture, per-pixel temporal std): "
            "V4L2 (gamma only) has 6.5x picamera2's noise (3.55 vs 0.55) "
            "because this path applies no noise reduction at all, while "
            "picamera2's ISP does by default. The product's real scenes are "
            "static/tracked astrophotography, so temporal accumulation (not "
            "spatial filtering) reduces noise without sacrificing spatial "
            "resolution. Lower = stronger reduction but slower response "
            "(~1/alpha frames to converge); any exposure or gain change "
            "clears the accumulator so frames of different brightness are "
            "never blended together"
        ),
    )
    camera_v4l2_temporal_nr_seconds: float = Field(
        default=2.0,
        ge=0.0,
        le=30.0,
        description=(
            "时域降噪的时间常数（秒），0 表示退回固定 alpha：短曝光下每秒有"
            "很多帧，多平均几十帧几乎不花墙钟时间，可以换到远强于固定 alpha "
            "的降噪；长曝光下每帧几秒，平均更多帧就是实打实的延迟，于是夹回 "
            "camera_v4l2_temporal_nr_alpha 这个上限 / Temporal-NR time "
            "constant in seconds; 0 falls back to the fixed alpha. Short "
            "exposures deliver many frames per second, so averaging tens of "
            "them costs almost no wall-clock time and buys far more denoise "
            "than a fixed alpha; long exposures cost seconds per frame, so "
            "averaging more is real latency and it clamps back to the "
            "camera_v4l2_temporal_nr_alpha bound"
        ),
    )
    camera_v4l2_temporal_nr_max_frames: int = Field(
        default=50,
        ge=1,
        le=500,
        description=(
            "时域降噪最多平均多少帧（短曝光下的上限）/ Maximum frames the "
            "temporal NR will average (the ceiling that short exposures hit)"
        ),
    )
    camera_v4l2_active_width: int = Field(
        default=1920, ge=160, description="传感器有效宽度 / Sensor active width"
    )
    camera_v4l2_active_height: int = Field(
        default=1080, ge=120, description="传感器有效高度 / Sensor active height"
    )
    camera_v4l2_line_duration_us: float = Field(
        default=0.0,
        ge=0.0,
        description="行周期覆盖值；0 自动推导 / Line-duration override; 0 derives it",
    )
    camera_v4l2_gain_db_per_step: float = Field(
        default=0.3,
        gt=0.0,
        description="模拟增益每步 dB / Analogue-gain dB per control step",
    )
    camera_v4l2_auto_gain_max: float = Field(
        default=16.0,
        ge=1.0,
        le=64.0,
        description="软件 AE 最大模拟增益 / Software-AE maximum analogue gain",
    )
    camera_v4l2_ae_target_background: float = Field(
        default=0.035,
        ge=0.005,
        le=0.25,
        description="夜空背景目标亮度 / Night-sky background target",
    )
    camera_v4l2_ae_target_highlight: float = Field(
        default=0.45,
        ge=0.05,
        le=0.95,
        description="星点高分位目标亮度 / Star-highlight percentile target",
    )
    camera_v4l2_ae_highlight_percentile: float = Field(
        default=99.8,
        ge=95.0,
        le=99.99,
        description="软件 AE 星点分位 / Software-AE star percentile",
    )
    camera_v4l2_ae_trace_enabled: bool = Field(
        default=False,
        description="写入有界 AE 诊断轨迹 / Write bounded AE diagnostic traces",
    )
    camera_v4l2_ae_trace_dir: Optional[Path] = Field(
        default=None,
        description="AE 诊断目录；为空时使用数据目录 / AE trace directory; data-dir default",
    )
    camera_v4l2_ae_trace_max_events: int = Field(
        default=2000,
        ge=1,
        le=100_000,
        description="每次 AE 轨迹最大事件数 / Maximum events per AE trace",
    )
    camera_v4l2_ae_trace_raw_sample_interval: int = Field(
        default=10,
        ge=1,
        le=10_000,
        description="每 N 帧保存降采样 RAW / Save sampled RAW every N frames",
    )
    camera_v4l2_ae_trace_max_raw_samples: int = Field(
        default=100,
        ge=0,
        le=10_000,
        description="每次轨迹最大 RAW 样本数 / Maximum RAW samples per trace",
    )
    camera_v4l2_ae_trace_raw_max_side: int = Field(
        default=320,
        ge=16,
        le=2048,
        description="诊断 RAW 样本最长边 / Diagnostic RAW sample maximum side",
    )
    camera_ae_polar_preset: bool = Field(
        default=True,
        description=(
            "启用 OGScope 自主星空场景 AE (Shadows/Matrix/Long+EV) / "
            "Enable OGScope autonomous starfield AE"
        ),
    )
    camera_ae_exposure_value: float = Field(
        default=1.0,
        ge=-2.0,
        le=2.0,
        description="星空 AE 曝光补偿(档) / Starfield AE exposure compensation in EV stops",
    )
    camera_ae_aggressive_enabled: bool = Field(
        default=True,
        description="根据暗部与高光占比动态提高极轴镜 AE / Dynamically bias polar AE toward dark detail",
    )
    camera_tuning_file: Optional[Path] = Field(
        default=None,
        description=(
            "Picamera2 tuning 覆盖路径；为空时使用随产品发布的 IMX327 tuning / "
            "Picamera2 tuning override path; bundled IMX327 tuning is used by default"
        ),
    )
    camera_auto_exposure_max_us: int = Field(
        default=3_000_000,
        ge=10_000,
        le=10_000_000,
        description=(
            "自动曝光最长帧周期 3s，暗场允许降帧 / Max auto-exposure frame "
            "duration, capped at 3s (raised from 1s 2026-09-20 after "
            "validating 1-3s manual exposure on real Zero2W hardware via "
            "the V4L2 backend - see "
            "docs/development/v4l2-zero2w-board-validation.md; the "
            "picamera2 backend keeps its own independent 1s ceiling, "
            "camera.py's AUTO_EXPOSURE_MAX_US, unaffected by this)"
        ),
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
    dev_captures_dir: Optional[Path] = Field(
        default=None,
        description=(
            "开发者相机拍摄持久化目录；None 时使用 data/dev_captures / "
            "Persistent developer-camera capture directory; defaults to data/dev_captures"
        ),
    )
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
        default=DEFAULT_EFFECTIVE_FOV_WIDTH_DEG,
        description=(
            "当前 IMX327 1280x720 + 16mm 镜头的有效水平视场(度) / "
            "Effective horizontal FOV for the current IMX327 1280x720 + 16mm capture"
        ),
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
    solver_centroid_sigma_v4l2: float = Field(
        default=2.1,
        description=(
            "V4L2 RAW 后端专用 σ 阈值：gamma 校正后画面对比度仍明显低于 "
            "picamera2/libcamera ISP 输出（尝试过再叠加 CLAHE 局部对比度增强，"
            "但在实测中只是放大暗部噪声、没有真正提升星点可探测性，已撤销 - "
            "见 docs/development/v4l2-zero2w-board-validation.md）。单独降低"
            "这条后端的阈值，而不是让画面在视觉上冒充 ISP 输出，才能大致复现 "
            "picamera2 在其默认 solver_centroid_sigma=2.5 下的检出数量级。"
            "但这个值不是精确常数：在真实 Zero2W 上重复拍摄，能对齐 picamera2 "
            "检出数的 σ 在不同轮次间落在约 1.9-2.2 之间（同一室内白天场景，"
            "曝光/噪声实现每次略有不同），2.1 取的是这个区间的中点，偏保守 "
            "（宁可少检出也不要让候选点数暴涨到 picamera2 的 3-4 倍，那样的一"
            "轮实测出现过）。在真实夜空验证前不要把这个数当作精确标定值 / "
            "Sigma threshold specific to the V4L2 RAW backend: even after "
            "gamma correction, contrast still trails picamera2/libcamera's "
            "ISP output measurably (a CLAHE local-contrast stage was tried "
            "on top but just amplified dark-region noise without improving "
            "real star detectability, and was reverted - see "
            "docs/development/v4l2-zero2w-board-validation.md). A "
            "separately-lowered threshold for this backend, not reshaping "
            "the image, is what roughly reproduces picamera2's own "
            "detection order-of-magnitude at its default "
            "solver_centroid_sigma=2.5 - but this isn't a precise constant: "
            "across repeated captures on real Zero2W hardware, the sigma "
            "that matches picamera2's count varied between ~1.9 and ~2.2 "
            "run to run (same indoor daylight scene, exposure/noise differ "
            "slightly each capture). 2.1 is the midpoint, chosen "
            "conservatively (better to under-detect than let the candidate "
            "count balloon to 3-4x picamera2's, which happened in one "
            "observed round). Do not treat this as a precisely calibrated "
            "value until validated against real night sky"
        ),
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
            "MJPEG 循环单次取帧（含编码线程）最大等待毫秒；超时表示相机取帧停滞 / "
            "Max wait per MJPEG frame fetch (incl. encode thread); timeout means camera fetch stalled"
        ),
    )
    stream_mjpeg_client_stall_timeout_ms: int = Field(
        default=30000,
        ge=0,
        le=300000,
        description=(
            "MJPEG 下游发送无进展的最大毫秒数；至少比取帧超时多 5 秒，0=禁用 / "
            "Max time without downstream MJPEG send progress; effectively at least 5s above "
            "frame-fetch timeout; 0=disabled"
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
    camera_capture_timeout_sec: float = Field(
        default=8.0,
        ge=0.5,
        le=120.0,
        description=(
            "单次相机抓帧硬超时（秒）；1 秒 AE 首帧需要包含多帧收敛预算 / "
            "Hard frame timeout; one-second AE startup needs a multi-frame convergence budget"
        ),
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
        default=120.0,
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

    @field_validator("camera_type", mode="before")
    @classmethod
    def _parse_camera_type(cls, value: object) -> str:
        """规范化可选相机后端并兼容旧别名 / Normalize backends and legacy aliases."""
        text = str(value or "imx327_mipi").strip().lower()
        if text in {"v4l2", "v4l2_raw", "linuxpy_v4l2", "v4l2_linuxpy"}:
            return "v4l2"
        return text

    @field_validator("camera_v4l2_bayer_pattern", mode="before")
    @classmethod
    def _parse_camera_v4l2_bayer_pattern(cls, value: object) -> str:
        """校验 Bayer 排列 / Validate the Bayer pattern."""
        text = str(value or "RGGB").strip().upper()
        return text if text in {"RGGB", "BGGR", "GRBG", "GBRG"} else "RGGB"

    @field_validator("camera_auto_exposure_max_us", mode="before")
    @classmethod
    def _cap_camera_auto_exposure_max_us(cls, value: object) -> object:
        """兼容旧配置并限制暗场曝光为 3s / Keep legacy config bootable and cap AE at 3s."""
        try:
            return min(3_000_000, int(value))
        except (TypeError, ValueError):
            return value

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
        if self.dev_captures_dir is None:
            object.__setattr__(self, "dev_captures_dir", self.data_dir / "dev_captures")
        # 创建必要的目录 / Create necessary directories
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        assert self.dev_captures_dir is not None
        self.dev_captures_dir.mkdir(parents=True, exist_ok=True)
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
