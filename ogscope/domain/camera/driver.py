"""相机驱动抽象 / Camera driver abstractions."""

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
    auto_exposure: bool = False
    software_auto_exposure: bool = False
    manual_exposure: bool = True
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

    def begin_fresh_capture_epoch(self) -> None:
        """新分析会话起点：清除任何跨帧历史状态 / Mark the start of a fresh
        analysis session so any cross-frame history (e.g. temporal noise
        reduction) is discarded before the next captured frame.

        预览通常在会话之间持续采集，一个新 frame_id 不代表帧内容不带旧历史
        （例如时域降噪的 EMA 累积器）。驱动若没有这类状态可以留空实现。
        Preview capture usually keeps running between sessions, so a newer
        frame_id alone doesn't guarantee the frame's content carries no old
        history (e.g. a temporal-NR EMA accumulator). Drivers with no such
        state can leave this a no-op.
        """
        ...
