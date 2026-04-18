"""
系统相关API路由
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ogscope.domain.system.services import system_info_service
from ogscope.platform.hardware_plane.runtime import get_hardware_plane_client
from ogscope.web.api.models.schemas import SystemInfo

router = APIRouter()


class HardwareCommandBody(BaseModel):
    """硬件命令体 / Hardware command body."""

    target: str
    action: str
    payload: dict = Field(default_factory=dict)


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
    )
