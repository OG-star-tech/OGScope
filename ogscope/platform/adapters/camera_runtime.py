"""迁移期间的旧实现适配 / Bridge the existing implementation during migration."""

from ogscope.domain.camera.runtime import CameraRuntime


def build_legacy_camera_runtime() -> CameraRuntime:
    """仅绑定已有实例，不创建第二个管理器 / Bind the existing instance without another manager."""
    from ogscope.web.api.debug.services import DebugCameraService
    from ogscope.web.camera_shared import get_camera_manager

    return CameraRuntime(capture=get_camera_manager(), control=DebugCameraService)
