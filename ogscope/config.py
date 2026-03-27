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
    camera_width: int = Field(default=640, description="图像宽度")
    camera_height: int = Field(default=360, description="图像高度")
    camera_fps: int = Field(default=15, description="帧率")
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
        default="sqlite:///./ogscope.db",
        description="数据库连接字符串"
    )
    
    # 文件路径配置 / File path configuration
    data_dir: Path = Field(default=Path("./data"), description="数据目录")
    upload_dir: Path = Field(default=Path("./uploads"), description="上传目录")
    analysis_dir: Path = Field(
        default=Path("./data/analysis"), description="分析任务目录"
    )
    catalog_dir: Path = Field(default=Path("./data/catalog"), description="星表目录")
    static_dir: Path = Field(default=Path("./web/static"), description="静态文件目录")
    template_dir: Path = Field(default=Path("./web/templates"), description="模板目录")

    # 星图解算配置 / Plate solving configuration
    solver_hint_ra_deg: float = Field(default=0.0, description="默认解算RA提示(度)")
    solver_hint_dec_deg: float = Field(default=90.0, description="默认解算Dec提示(度)")
    solver_fov_deg: float = Field(default=16.0, description="视场角(度)")
    solver_max_stars: int = Field(default=80, description="用于解算的最大星点数量")
    solver_fullsolve_interval_frames: int = Field(
        default=10, description="实时模式全量解算间隔帧数"
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
        self.catalog_dir.mkdir(parents=True, exist_ok=True)


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例 / Get configuration singleton"""
    return Settings()

