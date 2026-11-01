"""旧相机导入的兼容转发，不创建资源 / Legacy camera imports without resource ownership."""

from ogscope.application.camera_manager import (
    CameraManager,
    CapturedFrame,
    SharedFrame,
    get_camera_manager,
)

__all__ = ["CameraManager", "CapturedFrame", "SharedFrame", "get_camera_manager"]
