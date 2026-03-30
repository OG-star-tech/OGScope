"""
相机相关API路由 / Camera-related API routes
支持真实相机和模拟模式 / Supports real camera and simulation mode
"""

import io
import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

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
    if _simulation_mode:
        return {
            "connected": True,
            "streaming": _is_streaming,
            "resolution": [1920, 1080],
            "fps": 30,
            "mode": "simulation",
            "simulation_config": get_simulation_config(),
        }
    else:
        try:
            from ogscope.web.camera_shared import get_camera_manager

            status = await get_camera_manager().status()
            info = status.get("info", {}) if isinstance(status, dict) else {}
            width = int(info.get("output_width") or info.get("width") or 1920)
            height = int(info.get("output_height") or info.get("height") or 1080)
            fps = int(info.get("fps") or 30)
        except Exception as e:
            logger.error(f"读取相机状态失败: {e}")
            status = {"connected": False, "streaming": False}
            width, height, fps = 1920, 1080, 30

        return {
            "connected": bool(status.get("connected")),
            "streaming": bool(status.get("streaming")),
            "resolution": [int(width), int(height)],
            "fps": int(fps),
            "mode": "real",
            "runtime_overrides": status.get("runtime_overrides", {}),
        }


@router.get("/camera/preview")
async def get_camera_preview(since_frame_id: int | None = Query(default=None)):
    """获取相机预览图（JPEG） / Get camera preview (JPEG)"""
    if _simulation_mode:
        if not _is_streaming:
            # 返回静态占位符图像 / Return static placeholder image
            placeholder_image = io.BytesIO()
            placeholder_image.write(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x01\x90\x00\x00\x00\xf0\x08\x02\x00\x00\x00"
            )
            placeholder_image.seek(0)

            return StreamingResponse(
                placeholder_image,
                media_type="image/png",
                headers={"Cache-Control": "no-cache"},
            )

        # 生成虚拟视频帧 / Generate virtual video frames
        try:
            frame_data = _virtual_stream.generate_frame()
            return StreamingResponse(
                io.BytesIO(frame_data),
                media_type="image/jpeg",
                headers={"Cache-Control": "no-cache"},
            )
        except Exception as e:
            logger.error(f"生成虚拟视频帧失败: {e}")
            raise HTTPException(status_code=500, detail="生成视频帧失败")
    else:
        try:
            # 与调试台共用帧总线；通过 since_frame_id 减少重复 JPEG 下发。
            # Shared frame bus with debug console; use since_frame_id to avoid duplicate payload.
            from ogscope.web.api.debug.services import DebugCameraService

            return await DebugCameraService.get_preview(since_frame_id=since_frame_id)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"获取真实相机预览失败: {e}")
            raise HTTPException(status_code=500, detail="获取预览失败")
