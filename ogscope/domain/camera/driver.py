"""相机驱动抽象与未来 Linuxpy 入口 / Camera driver abstractions and future Linuxpy hook."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class FrameBuffer:
    """跨驱动帧载体；data 可为 ndarray、bytes 或 memoryview / Cross-driver frame carrier."""

    data: Any
    width: int
    height: int
    pixel_format: str = "RGB888"
    timestamp: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CameraCapabilities:
    """驱动能力描述，供 API 与前端安全降级 / Driver capability description for API/UI fallback."""

    driver: str = "unknown"
    backend: str = "unknown"
    lores_stream: bool = False
    lores_width: int = 0
    lores_height: int = 0
    lores_format: str = ""
    awb_modes: tuple[str, ...] = ("auto", "manual", "night")
    ae_flicker: bool = False
    noise_reduction_modes: tuple[str, ...] = ("off", "fast", "high_quality")
    manual_digital_gain: bool = False
    autofocus: bool = False
    hdr: bool = False


class CameraDriver(Protocol):
    """最小相机驱动协议 / Minimal camera driver protocol."""

    is_initialized: bool
    is_capturing: bool

    def initialize(self) -> bool: ...

    def start_capture(self) -> bool: ...

    def stop_capture(self) -> bool: ...

    def get_video_frame(self) -> Any: ...

    def get_camera_info(self) -> dict[str, Any]: ...


class LinuxpyV4L2Driver:
    """Linuxpy/V4L2 预留骨架；本轮不作为树莓派 CSI 默认路径 / Reserved linuxpy/V4L2 stub."""

    is_initialized = False
    is_capturing = False

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def initialize(self) -> bool:
        """真实 linuxpy 适配将在自定义 Linux 系统中实现 / Real linuxpy adapter is implemented later."""
        raise NotImplementedError(
            "linuxpy driver is reserved but not implemented / linuxpy 驱动已预留但未实现"
        )
