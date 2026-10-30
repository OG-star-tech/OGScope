"""统一绑定相机运行实例 / Compose one shared camera runtime."""

from threading import Lock

from ogscope.domain.camera.runtime import CameraCapture, CameraControl, CameraRuntime

_runtime: CameraRuntime | None = None
_binding_lock = Lock()


def get_camera_runtime() -> CameraRuntime:
    """延迟绑定一次，不打开硬件；局部服务通过构造参数注入 / Bind once without opening hardware."""
    global _runtime
    if _runtime is None:
        with _binding_lock:
            if _runtime is None:
                from ogscope.platform.adapters.camera_runtime import (
                    build_legacy_camera_runtime,
                )

                _runtime = build_legacy_camera_runtime()
    return _runtime


def get_camera_capture() -> CameraCapture:
    """控制、分析、预览及生命周期共用同一采集端口 / Share capture across all runtime consumers."""
    return get_camera_runtime().capture


def get_camera_control() -> CameraControl:
    """兼容入口与领域共用同一控制实现 / Share controls across compatibility and domain callers."""
    return get_camera_runtime().control
