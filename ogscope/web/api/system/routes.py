"""
系统相关API路由
"""

from fastapi import APIRouter

from ogscope.web.api.models.schemas import SystemInfo
from ogscope.domain.system.services import system_info_service

router = APIRouter()


@router.get("/system/info", response_model=SystemInfo)
async def get_system_info() -> SystemInfo:
    """获取系统信息 / Get system information"""
    return SystemInfo(**system_info_service.get_system_info())
