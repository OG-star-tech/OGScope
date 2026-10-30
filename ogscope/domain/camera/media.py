"""Core 与 Dev 共用的媒体元数据读取 / Media metadata reads shared by Core and Dev."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ogscope.domain.camera.sidecar import merge_capture_sidecar_into_info
from ogscope.domain.shared import filesystem
from ogscope.domain.shared.filesystem import (
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    dev_captures_storage_info,
    ensure_safe_basename,
)


class CameraMediaCatalog:
    """目录可注入；不负责拍摄、删除或配置持久化 / Injectable read-only catalog, independent of capture and persistence."""

    def __init__(self, directory: Path | None = None) -> None:
        self._directory = directory

    @property
    def directory(self) -> Path:
        return (
            self._directory
            if self._directory is not None
            else filesystem.DEV_CAPTURES_DIR
        )

    async def get_files(self) -> dict[str, Any]:
        """获取拍摄文件列表 / Get shooting file list"""
        try:
            files: list[dict[str, Any]] = []
            for file_path in self.directory.iterdir():
                if file_path.is_file():
                    suffix = file_path.suffix.lower()
                    if suffix in IMAGE_EXTENSIONS or suffix in VIDEO_EXTENSIONS:
                        files.append(
                            {
                                "name": file_path.name,
                                "size": file_path.stat().st_size,
                                "modified": datetime.fromtimestamp(
                                    file_path.stat().st_mtime
                                ).isoformat(),
                                "type": (
                                    "image" if suffix in IMAGE_EXTENSIONS else "video"
                                ),
                            }
                        )

            # 按修改时间排序（最新的在前） / Sort by modification time (newest first)
            files.sort(key=lambda x: x["modified"], reverse=True)

            return {
                "files": files,
                "storage": dev_captures_storage_info(self.directory),
            }

        except Exception as e:
            raise Exception(f"获取文件列表失败: {str(e)}")

    async def get_file_info(self, filename: str) -> dict[str, Any]:
        """获取文件信息 / Get file information"""
        safe_name = ensure_safe_basename(filename)
        file_path = self.directory / safe_name
        info_path = self.directory / f"{file_path.stem}.txt"

        if not file_path.exists():
            raise Exception("文件不存在")

        try:
            suffix = file_path.suffix.lower()
            file_type = "image" if suffix in IMAGE_EXTENSIONS else "video"

            info = {
                "filename": filename,
                "size": file_path.stat().st_size,
                "modified": datetime.fromtimestamp(
                    file_path.stat().st_mtime
                ).isoformat(),
                "type": file_type,
            }

            # 读取拍摄信息；将 camera 内字段展开到顶层以兼容前端详情 / Read sidecar; flatten camera for UI
            if info_path.exists():
                with open(info_path, encoding="utf-8") as f:
                    capture_info = json.load(f)
                    if isinstance(capture_info, dict):
                        merge_capture_sidecar_into_info(info, capture_info)

            return info

        except Exception as e:
            raise Exception(f"获取文件信息失败: {str(e)}")
