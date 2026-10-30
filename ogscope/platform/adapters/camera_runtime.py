"""将现有采集管理器绑定到中性控制 / Bind existing capture to neutral controls."""

from ogscope.application.camera_control import CameraControlService
from ogscope.domain.camera.runtime import CameraRuntime


def _analysis_running() -> bool:
    """保留分析启动窗口内的停机保护 / Preserve stop protection during analysis startup."""
    from ogscope.core.realtime import realtime_solve_service

    return bool(realtime_solve_service.state.running)


def build_camera_runtime() -> CameraRuntime:
    """中性控制复用已有管理器，不加载 Web Debug / Reuse existing capture without loading Web Debug."""
    from ogscope.application.camera_manager import get_camera_manager

    capture = get_camera_manager()
    return CameraRuntime(
        capture=capture,
        control=CameraControlService(capture, analysis_running=_analysis_running),
    )
