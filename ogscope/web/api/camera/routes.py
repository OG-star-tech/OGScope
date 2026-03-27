"""
相机相关API路由 / Camera-related API routes
支持真实相机和模拟模式 / Supports real camera and simulation mode
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from ogscope.utils.environment import should_use_simulation_mode, get_simulation_config
from ogscope.hardware.camera import create_camera
from ogscope.utils.virtual_stream import get_virtual_stream
import logging
import io

logger = logging.getLogger(__name__)
router = APIRouter()

_camera_instance = None
_is_streaming = False
_simulation_mode = should_use_simulation_mode()

if _simulation_mode:
    logger.info("检测到非树莓派环境，启用模拟模式")
    _virtual_stream = get_virtual_stream()
else:
    logger.info("检测到树莓派环境，使用真实相机")
    _camera_instance = None


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
            "simulation_config": get_simulation_config()
        }
    else:
        connected = False
        streaming = False
        width, height, fps = 1920, 1080, 30
        try:
            global _camera_instance
            if _camera_instance is not None:
                connected = getattr(_camera_instance, "is_initialized", False)
                streaming = getattr(_camera_instance, "is_capturing", False)
                width = getattr(_camera_instance, "width", width)
                height = getattr(_camera_instance, "height", height)
                fps = getattr(_camera_instance, "fps", fps)
        except Exception as e:
            logger.error(f"读取相机状态失败: {e}")

        return {
            "connected": bool(connected),
            "streaming": bool(streaming),
            "resolution": [int(width), int(height)],
            "fps": int(fps),
            "mode": "real"
        }


@router.get("/camera/preview")
async def get_camera_preview():
    """获取相机预览图（JPEG） / Get camera preview (JPEG)"""
    if _simulation_mode:
        if not _is_streaming:
            # 返回静态占位符图像 / Return static placeholder image
            placeholder_image = io.BytesIO()
            placeholder_image.write(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x01\x90\x00\x00\x00\xf0\x08\x02\x00\x00\x00')
            placeholder_image.seek(0)
            
            return StreamingResponse(
                placeholder_image,
                media_type="image/png",
                headers={"Cache-Control": "no-cache"}
            )
        
        # 生成虚拟视频帧 / Generate virtual video frames
        try:
            frame_data = _virtual_stream.generate_frame()
            return StreamingResponse(
                io.BytesIO(frame_data),
                media_type="image/jpeg",
                headers={"Cache-Control": "no-cache"}
            )
        except Exception as e:
            logger.error(f"生成虚拟视频帧失败: {e}")
            raise HTTPException(status_code=500, detail="生成视频帧失败")
    else:
        try:
            global _camera_instance
            # 懒加载初始化与启动，避免前端必须显式调用 start / Lazy loading initialization and startup to avoid the front end having to explicitly call start
            if _camera_instance is None or not getattr(_camera_instance, "is_initialized", False):
                from ogscope.config import get_settings
                settings = get_settings()
                cam_cfg = {
                    "width": getattr(settings, "camera_width", 640),
                    "height": getattr(settings, "camera_height", 360),
                    "fps": getattr(settings, "camera_fps", 5),
                    "exposure_us": getattr(settings, "camera_exposure", 10000),
                    "analogue_gain": getattr(settings, "camera_gain", 1.0),
                    "digital_gain": getattr(settings, "camera_digital_gain", 1.0),
                    "auto_exposure": getattr(settings, "camera_auto_exposure", False),
                    "auto_gain": getattr(settings, "camera_auto_gain", False),
                    "rotation": getattr(settings, "camera_rotation", 0),
                    "sampling_mode": getattr(settings, "camera_sampling_mode", "supersample"),
                    "type": getattr(settings, "camera_type", "imx327_mipi"),
                }
                _camera_instance = create_camera(cam_cfg)
                if _camera_instance is None:
                    raise HTTPException(status_code=500, detail="创建相机失败")
                if not _camera_instance.initialize():
                    raise HTTPException(status_code=500, detail="相机初始化失败")
            if not getattr(_camera_instance, "is_capturing", False):
                if not _camera_instance.start_capture():
                    raise HTTPException(status_code=500, detail="相机未能启动")

            # 获取一帧并编码为JPEG / Get a frame and encode to JPEG
            frame = _camera_instance.get_video_frame()
            if frame is None:
                raise HTTPException(status_code=500, detail="无法获取视频帧")
            try:
                import cv2
                ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if not ok:
                    raise RuntimeError("图像编码失败")
                data = buf.tobytes()
            except Exception as e:
                logger.error(f"编码JPEG失败: {e}")
                raise HTTPException(status_code=500, detail="编码失败")

            return StreamingResponse(
                io.BytesIO(data),
                media_type="image/jpeg",
                headers={"Cache-Control": "no-cache"}
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"获取真实相机预览失败: {e}")
            raise HTTPException(status_code=500, detail="获取预览失败")

