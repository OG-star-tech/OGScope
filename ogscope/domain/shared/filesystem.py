"""
文件系统共享常量与安全工具 / Shared filesystem constants and safety utilities.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterable
from pathlib import Path, PurePath

from ogscope.config import get_settings

_configured_dev_captures_dir = get_settings().dev_captures_dir
assert _configured_dev_captures_dir is not None
DEV_CAPTURES_DIR = Path(_configured_dev_captures_dir)
DEV_CAPTURES_DIR.mkdir(parents=True, exist_ok=True)

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


def dev_captures_storage_info(path: Path = DEV_CAPTURES_DIR) -> dict[str, object]:
    """返回调试拍摄目录的持久化语义 / Describe capture storage persistence."""
    resolved = path.expanduser().resolve()
    volatile_roots = (Path("/tmp").resolve(), Path("/run").resolve())
    is_temporary = any(
        resolved == root or root in resolved.parents for root in volatile_roots
    )
    return {
        "path": str(resolved),
        "persistence": "temporary" if is_temporary else "persistent",
        "is_persistent": not is_temporary,
    }


def migrate_legacy_dev_captures(
    legacy_dirs: Iterable[Path] | None = None,
    target_dir: Path = DEV_CAPTURES_DIR,
) -> dict[str, object]:
    """
    无覆盖迁移历史调试拍摄文件 / Migrate legacy captures without overwriting.

    源文件保留不删，避免更新中断时两边都丢失。
    Source files stay in place so an interrupted update cannot lose both copies.
    """
    target = target_dir.expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    sources = tuple(
        (Path("/tmp/dev_captures"), Path.home() / "dev_captures")
        if legacy_dirs is None
        else legacy_dirs
    )
    migrated: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    for source_dir in sources:
        source = source_dir.expanduser().resolve()
        if source == target or not source.is_dir():
            continue
        try:
            source_paths = sorted(source.iterdir(), key=lambda item: item.name)
        except OSError as exc:
            errors.append(f"{source}: {exc}")
            continue
        for source_path in source_paths:
            if not source_path.is_file() or source_path.is_symlink():
                continue
            try:
                safe_name = ensure_safe_basename(source_path.name)
                destination = target / safe_name
                if destination.exists():
                    skipped.append(safe_name)
                    continue
                temporary = target / f".{safe_name}.migrating-{os.getpid()}"
                try:
                    shutil.copy2(source_path, temporary)
                    os.replace(temporary, destination)
                finally:
                    temporary.unlink(missing_ok=True)
                migrated.append(safe_name)
            except (OSError, ValueError) as exc:
                errors.append(f"{source_path}: {exc}")

    return {"migrated": migrated, "skipped": skipped, "errors": errors}
