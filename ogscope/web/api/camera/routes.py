"""
相机相关API路由 / Camera-related API routes
支持真实相机和模拟模式 / Supports real camera and simulation mode
"""

import logging

from fastapi import APIRouter, Query

from ogscope.domain.camera.services import camera_domain_service
from ogscope.utils.environment import get_simulation_config, should_use_simulation_mode
from ogscope.utils.virtual_stream import get_virtual_stream

logger = logging.getLogger(__name__)
router = APIRouter()

_is_streaming = False
_simulation_mode = should_use_simulation_mode()

if _simulation_mode:
    logger.info("检测到非树莓派环境，启用模拟模式")
    _virtual_stream = get_virtual_stream()
else:
    logger.info("检测到树莓派环境，使用真实相机（与调试/分析共用单例）")


@router.get("/camera/status")
async def get_camera_status():
    """获取相机状态 / Get camera status"""
    return await camera_domain_service.get_product_camera_status(
        simulation_mode=_simulation_mode,
        is_streaming=_is_streaming,
        simulation_config=get_simulation_config(),
    )


@router.get("/camera/preview")
async def get_camera_preview(since_frame_id: int | None = Query(default=None)):
    """获取相机预览图（JPEG） / Get camera preview (JPEG)"""
    return await camera_domain_service.get_product_camera_preview(
        simulation_mode=_simulation_mode,
        is_streaming=_is_streaming,
        virtual_stream=_virtual_stream if _simulation_mode else None,
        since_frame_id=since_frame_id,
    )
