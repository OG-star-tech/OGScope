"""
文件系统共享常量与安全工具 / Shared filesystem constants and safety utilities.
"""

from __future__ import annotations

from pathlib import Path, PurePath

DEV_CAPTURES_DIR = Path.home() / "dev_captures"
DEV_CAPTURES_DIR.mkdir(exist_ok=True)

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tiff",
    ".tif",
    ".webp",
}

VIDEO_EXTENSIONS = {
    ".mp4",
    ".avi",
    ".mov",
    ".mkv",
    ".wmv",
    ".flv",
    ".webm",
    ".m4v",
}


def ensure_safe_basename(filename: str) -> str:
    """限制为单层 basename，防止路径穿越 / Allow basename only to prevent traversal."""
    safe_name = PurePath(filename).name
    if not safe_name or safe_name != filename or safe_name in {".", ".."}:
        raise ValueError("invalid filename")
    if "/" in safe_name or "\\" in safe_name:
        raise ValueError("invalid filename")
    return safe_name

