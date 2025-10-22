"""
相机相关API路由
支持真实相机和模拟模式
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from ogscope.web.api.models.schemas import CameraSettings
from ogscope.utils.environment import should_use_simulation_mode, get_simulation_config
from ogscope.utils.virtual_stream import get_virtual_stream
import logging
import io

logger = logging.getLogger(__name__)
router = APIRouter()

# 全局状态
_camera_instance = None
_is_streaming = False
_simulation_mode = should_use_simulation_mode()

if _simulation_mode:
    logger.info("检测到非树莓派环境，启用模拟模式")
    _virtual_stream = get_virtual_stream()
else:
    logger.info("检测到树莓派环境，使用真实相机")


@router.get("/camera/status")
async def get_camera_status():
    """获取相机状态"""
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
        # TODO: 实现真实相机状态获取
        return {
            "connected": False,
            "streaming": False,
            "resolution": [1920, 1080],
            "fps": 30,
            "mode": "real"
        }


@router.post("/camera/settings")
async def update_camera_settings(settings: CameraSettings):
    """更新相机设置"""
    if _simulation_mode:
        logger.info(f"模拟模式：更新相机设置 {settings}")
        return {
            "success": True,
            "settings": settings.dict(),
            "mode": "simulation"
        }
    else:
        # TODO: 实现真实相机设置更新
        return {
            "success": True,
            "settings": settings.dict(),
            "mode": "real"
        }


@router.get("/camera/config")
async def get_camera_config():
    """获取相机配置"""
    from ogscope.config import get_settings
    settings = get_settings()
    
    if _simulation_mode:
        return {
            "type": "virtual",
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "exposure_us": 10000,
            "gain": 1.0,
            "mode": "simulation"
        }
    else:
        return {
            "type": settings.camera_type,
            "width": settings.camera_width,
            "height": settings.camera_height,
            "fps": settings.camera_fps,
            "exposure_us": settings.camera_exposure,
            "gain": settings.camera_gain,
            "mode": "real"
        }


@router.post("/camera/config")
async def update_camera_config(config: dict):
    """更新相机配置"""
    if _simulation_mode:
        logger.info(f"模拟模式：更新相机配置 {config}")
        
        # 更新虚拟流参数
        if 'exposure_us' in config:
            logger.info(f"模拟曝光时间: {config['exposure_us']}μs")
        
        if 'analogue_gain' in config:
            logger.info(f"模拟增益: {config['analogue_gain']}")
        
        return {"status": "success", "config": config, "mode": "simulation"}
    else:
        # TODO: 实现真实相机配置更新逻辑
        return {"status": "success", "config": config, "mode": "real"}


@router.post("/camera/start")
async def start_camera():
    """开始相机预览"""
    global _is_streaming
    
    if _simulation_mode:
        _is_streaming = True
        logger.info("模拟模式：开始视频流")
        return {"status": "success", "message": "模拟视频流已开始", "mode": "simulation"}
    else:
        # TODO: 实现真实相机启动逻辑
        _is_streaming = True
        return {"status": "success", "message": "相机预览已开始", "mode": "real"}


@router.post("/camera/stop")
async def stop_camera():
    """停止相机预览"""
    global _is_streaming
    
    if _simulation_mode:
        _is_streaming = False
        logger.info("模拟模式：停止视频流")
        return {"status": "success", "message": "模拟视频流已停止", "mode": "simulation"}
    else:
        # TODO: 实现真实相机停止逻辑
        _is_streaming = False
        return {"status": "success", "message": "相机预览已停止", "mode": "real"}


@router.get("/camera/preview")
async def get_camera_preview():
    """获取相机预览图（JPEG）"""
    if _simulation_mode:
        if not _is_streaming:
            # 返回静态占位符图像
            placeholder_image = io.BytesIO()
            placeholder_image.write(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x01\x90\x00\x00\x00\xf0\x08\x02\x00\x00\x00')
            placeholder_image.seek(0)
            
            return StreamingResponse(
                placeholder_image,
                media_type="image/png",
                headers={"Cache-Control": "no-cache"}
            )
        
        # 生成虚拟视频帧
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
        # TODO: 实现真实相机预览图获取
        placeholder_image = io.BytesIO()
        placeholder_image.write(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x01\x90\x00\x00\x00\xf0\x08\x02\x00\x00\x00')
        placeholder_image.seek(0)
        
        return StreamingResponse(
            placeholder_image,
            media_type="image/png",
            headers={"Cache-Control": "no-cache"}
        )


@router.get("/camera/stars")
async def get_star_positions():
    """获取星点位置信息（用于校准）"""
    if _simulation_mode:
        try:
            stars = _virtual_stream.get_star_positions()
            return {
                "stars": stars,
                "count": len(stars),
                "mode": "simulation"
            }
        except Exception as e:
            logger.error(f"获取模拟星点位置失败: {e}")
            raise HTTPException(status_code=500, detail="获取星点位置失败")
    else:
        # TODO: 实现真实星点检测
        return {
            "stars": [],
            "count": 0,
            "mode": "real"
        }


@router.post("/camera/simulation/update-polar-star")
async def update_polar_star_position(x: float, y: float):
    """更新极轴星位置（仅模拟模式）"""
    if not _simulation_mode:
        raise HTTPException(status_code=400, detail="此功能仅在模拟模式下可用")
    
    try:
        _virtual_stream.update_polar_star_position(x, y)
        return {
            "status": "success",
            "message": f"极轴星位置已更新为 ({x}, {y})",
            "polar_star_position": {"x": x, "y": y}
        }
    except Exception as e:
        logger.error(f"更新极轴星位置失败: {e}")
        raise HTTPException(status_code=500, detail="更新极轴星位置失败")


@router.post("/camera/simulation/parameters")
async def update_simulation_parameters(parameters: dict):
    """更新模拟参数（仅模拟模式）"""
    if not _simulation_mode:
        raise HTTPException(status_code=400, detail="此功能仅在模拟模式下可用")
    
    try:
        _virtual_stream.set_simulation_parameters(**parameters)
        return {
            "status": "success",
            "message": "模拟参数已更新",
            "parameters": parameters
        }
    except Exception as e:
        logger.error(f"更新模拟参数失败: {e}")
        raise HTTPException(status_code=500, detail="更新模拟参数失败")