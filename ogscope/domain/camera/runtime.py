"""中性相机运行端口；不依赖 Web 或具体驱动 / Camera runtime ports without Web or driver imports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol, runtime_checkable

from ogscope.domain.camera.readiness import CaptureReadiness


@dataclass(slots=True)
class SharedFrame:
    """共享帧的中性值对象 / Neutral shared frame value."""

    frame_id: int
    timestamp: float
    raw_frame: Any | None
    jpeg_frame: bytes | None
    width: int
    height: int
    source_format: str = "RGB888"


@runtime_checkable
class CameraCapture(Protocol):
    """单设备生命周期、帧与占用端口 / Single-device lifetime, frame and ownership port.

    保留现有公共操作，不暴露内部锁、线程或状态布尔值；拆分实现留待后续。
    Preserve public operations without exposing locks, workers or state flags; split implementation later.
    """

    analysis_readiness: CaptureReadiness

    @property
    def preview_jpeg_quality(self) -> int: ...

    @property
    def preview_target_fps(self) -> int: ...

    async def ensure_started(self, *, start_grabber: bool = False) -> None: ...

    async def acquire_preview_consumer(self) -> None: ...

    async def release_preview_consumer(self) -> None: ...

    async def acquire_analysis_consumer(self) -> None: ...

    async def release_analysis_consumer(self) -> None: ...

    async def acquire_recording_consumer(self) -> None: ...

    async def release_recording_consumer(self) -> None: ...

    def update_operation_lease(
        self,
        *,
        lease_id: str | None = None,
        release: bool = False,
        ttl_seconds: float = 60.0,
    ) -> dict[str, Any]: ...

    def lifecycle_status(self) -> dict[str, Any]: ...

    async def stop(self, *, force: bool = False) -> None: ...

    async def pause_grabber(self) -> None: ...

    async def resume_grabber(self) -> None: ...

    async def reconfigure_camera(
        self, operation_name: str, fn: Callable[[], Any], *, timeout_sec: float = 10.0
    ) -> Any: ...

    def get_camera_instance(self): ...

    def attach_camera_instance(self, camera: Any) -> None: ...

    async def status(self) -> dict[str, Any]: ...

    async def get_preview_frame(
        self, since_id: int | None = None, wait_timeout_sec: float = 0.8
    ) -> tuple[int, SharedFrame | None]: ...

    async def get_raw_frame(self) -> tuple[Any, int, float]: ...

    async def reset_temporal_history(self, camera: Any) -> bool: ...

    def get_current_capture_sequence(self) -> int: ...

    async def get_cached_frame_snapshot(self) -> SharedFrame | None: ...

    async def get_stream_jpeg(
        self, snap: SharedFrame, quality: int
    ) -> bytes | None: ...

    @staticmethod
    def encode_frame(
        raw_frame: Any, image_format: str = "jpeg", quality: int = 75
    ) -> bytes | None: ...

    def update_runtime_overrides(self, updates: dict[str, Any]) -> None: ...

    def set_preview_fps(self, fps: int) -> int: ...

    async def stream_metrics(self) -> dict[str, Any]: ...

    def get_runtime_overrides(self) -> dict[str, Any]: ...

    def clear_runtime_overrides(self) -> None: ...


@runtime_checkable
class CameraControl(Protocol):
    """Core 与 Dev 共用的控制投影 / Control projection shared by Core and Dev.

    返回帧值而非 HTTP 响应；共享控制状态由单个实现持有。
    Return frame values rather than HTTP responses; one implementation owns shared control state.
    """

    recording: bool

    async def get_camera_status(self) -> dict[str, Any]: ...

    async def get_runtime_overrides(self) -> dict[str, Any]: ...

    async def clear_runtime_overrides(self) -> dict[str, Any]: ...

    async def start_camera(self) -> dict[str, Any]: ...

    async def ensure_camera_streaming(self) -> None: ...

    async def stop_camera(self) -> dict[str, Any]: ...

    async def get_preview_frame(
        self, since_frame_id: int | None = None
    ) -> tuple[int, SharedFrame | None]: ...

    async def start_focus_session(self) -> dict[str, Any]: ...

    async def stop_focus_session(self) -> dict[str, Any]: ...

    async def get_stream_frame_bytes(
        self,
        image_format: str = "jpeg",
        quality: int = 75,
        *,
        since_frame_id: int | None = None,
    ) -> tuple[int, bytes | None, int]: ...

    async def set_rotation(self, rotation: int) -> dict[str, Any]: ...

    async def set_mirror(
        self, flip_horizontal: bool, flip_vertical: bool
    ) -> dict[str, Any]: ...

    async def set_size(self, width: int, height: int) -> dict[str, Any]: ...

    async def set_sampling_mode(self, mode: str) -> dict[str, Any]: ...

    async def set_fps(self, fps: int) -> dict[str, Any]: ...

    async def set_auto_exposure_mode(self, enabled: bool) -> dict[str, Any]: ...

    async def update_settings(self, settings: dict[str, Any]) -> dict[str, Any]: ...

    async def set_white_balance(
        self, mode: str, gain_r: float = 1.0, gain_b: float = 1.0
    ) -> dict[str, Any]: ...

    async def set_color_mode(self, color_mode: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class CameraRuntime:
    """一次绑定控制与采集，避免各调用方拥有不同硬件 / Bind control and capture as one runtime."""

    capture: CameraCapture
    control: CameraControl
