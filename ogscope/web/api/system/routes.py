"""
系统相关API路由
"""
from fastapi import APIRouter
from ogscope.web.api.models.schemas import SystemInfo

router = APIRouter()


@router.get("/system/info")
async def get_system_info():
    """获取系统信息"""
    # TODO: 实现系统信息获取
    return {
        "platform": "Orange Pi Zero 2W",
        "os": "Debian",
        "cpu_usage": 0.0,
        "memory_usage": 0.0,
        "temperature": 0.0,
    }
