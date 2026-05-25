"""
系统相关API路由
"""

from pathlib import Path
import os
import subprocess

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ogscope.config import get_settings
from ogscope.config_catalog import build_config_catalog
from ogscope.domain.system.services import system_info_service
from ogscope.platform.hardware_plane.runtime import get_hardware_plane_client
from ogscope.web.api.models.schemas import SystemInfo

router = APIRouter()


class HardwareCommandBody(BaseModel):
    """硬件命令体 / Hardware command body."""

    target: str
    action: str
    payload: dict = Field(default_factory=dict)
    timeout_ms: int | None = Field(
        default=None,
        ge=100,
        le=10000,
        description="可选 RPC 超时（毫秒），大屏刷新等可加长 / Optional RPC timeout for slow ops",
    )


class ConfigFileUpdateBody(BaseModel):
    """配置文件更新请求 / Config file update payload."""

    file_id: str = Field(..., description="配置文件标识 / Config file identifier")
    content: str = Field(..., description="完整文件内容 / Full file content")


_CONFIG_FILE_MAP: dict[str, Path] = {
    "ogscope": Path("/etc/ogscope/ogscope.env"),
    "network": Path("/etc/ogscope/network.env"),
}


def _validate_env_content(content: str) -> None:
    for idx, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        candidate = stripped[7:] if stripped.startswith("export ") else stripped
        if "=" not in candidate:
            raise HTTPException(
                status_code=400,
                detail=f"invalid env line at {idx}: missing '='",
            )


def _read_config_file(path: Path) -> dict:
    exists = path.exists()
    writable = os.access(path if exists else path.parent, os.W_OK)
    if not exists:
        return {
            "path": str(path),
            "exists": False,
            "writable": writable,
            "content": "",
            "error": "file not found",
        }
    try:
        content = path.read_text(encoding="utf-8")
        return {
            "path": str(path),
            "exists": True,
            "writable": writable,
            "content": content,
            "error": None,
        }
    except OSError as exc:
        return {
            "path": str(path),
            "exists": True,
            "writable": writable,
            "content": "",
            "error": str(exc),
        }


def _write_config_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(content, encoding="utf-8")
        return
    except OSError:
        pass

    proc = subprocess.run(
        ["sudo", "-n", "tee", str(path)],
        input=content,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=(
                "failed to write config file; grant write permission "
                "or allow sudo tee without password"
            ),
        )
    subprocess.run(
        ["sudo", "-n", "chmod", "640", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )


@router.get("/system/info", response_model=SystemInfo)
async def get_system_info() -> SystemInfo:
    """获取系统信息 / Get system information"""
    return SystemInfo(**system_info_service.get_system_info())


@router.get("/system/hardware-plane/status")
async def get_hardware_plane_status() -> dict:
    """获取硬件平面状态 / Get hardware-plane status."""
    client = get_hardware_plane_client()
    return await client.status_get()


@router.get("/system/hardware-plane/metrics")
async def get_hardware_plane_metrics() -> dict:
    """获取硬件平面指标 / Get hardware-plane metrics."""
    client = get_hardware_plane_client()
    status = await client.status_get()
    if not status.get("success"):
        return status
    data = status.get("data", {})
    return {
        "success": True,
        "data": {
            "metrics": data.get("metrics", {}),
            "services": list((data.get("services", {}) or {}).keys()),
            "started": bool(data.get("started", False)),
            "profile": data.get("profile", {}),
        },
        "error": None,
    }


@router.get("/system/hardware-plane/sensors/{sensor_name}")
async def get_hardware_sensor(sensor_name: str) -> dict:
    """读取硬件传感器值 / Read hardware sensor value."""
    client = get_hardware_plane_client()
    return await client.sensor_read(f"sensor.{sensor_name}")


@router.post("/system/hardware-plane/command")
async def post_hardware_command(body: HardwareCommandBody) -> dict:
    """发送硬件控制命令 / Send hardware control command."""
    client = get_hardware_plane_client()
    return await client.device_command(
        target=body.target,
        action=body.action,
        payload=dict(body.payload),
        timeout_ms=body.timeout_ms,
    )


@router.get("/system/config/catalog")
async def get_system_config_catalog() -> dict:
    """返回配置项目录（键名、默认值、双语说明）/ Config key catalog with defaults and descriptions."""
    return {"success": True, **build_config_catalog()}


@router.get("/system/config/files")
async def get_system_config_files() -> dict:
    files = []
    for file_id, path in _CONFIG_FILE_MAP.items():
        payload = _read_config_file(path)
        payload["file_id"] = file_id
        files.append(payload)
    return {"success": True, "files": files}


@router.post("/system/config/files")
async def update_system_config_file(body: ConfigFileUpdateBody) -> dict:
    path = _CONFIG_FILE_MAP.get(body.file_id)
    if path is None:
        raise HTTPException(status_code=404, detail="unknown config file")
    _validate_env_content(body.content)
    _write_config_file(path, body.content)
    get_settings.cache_clear()
    return {
        "success": True,
        "message": f"saved {body.file_id}",
        "restart_required": True,
    }
