"""
调试控制台API路由
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse
from ogscope.web.api.models.schemas import CameraSettings, CameraPreset
from ogscope.web.api.debug.services import (
    DebugCameraService, 
    DebugPresetService, 
    DebugFileService
)

router = APIRouter()


# ==================== 相机控制 ====================

@router.get("/debug/camera/status")
async def get_debug_camera_status():
    """获取调试相机状态"""
    try:
        return await DebugCameraService.get_camera_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/start")
async def start_debug_camera():
    """启动调试相机"""
    try:
        return await DebugCameraService.start_camera()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/camera/stream")
async def stream_debug_camera(quality: int = Query(70, ge=10, le=100)):
    """MJPEG 实时流 - 可配置压缩质量"""
    try:
        from ogscope.web.api.debug.services import DebugCameraService
        camera = DebugCameraService.get_camera_instance()
        if not camera or not camera.is_capturing:
            raise HTTPException(status_code=503, detail="相机未运行")

        import cv2
        import numpy as np

        boundary = "frame"

        async def frame_generator():
            while True:
                frame = camera.get_video_frame()
                if frame is None:
                    break
                ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
                if not ok:
                    continue
                data = buf.tobytes()
                yield (
                    b"--" + boundary.encode() + b"\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(data)).encode() + b"\r\n\r\n" + data + b"\r\n"
                )

        return StreamingResponse(frame_generator(), media_type=f"multipart/x-mixed-replace; boundary={boundary}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/camera/stream-lossless")
async def stream_debug_camera_lossless():
    """无损质量实时流 - 使用PNG格式展示超采样效果"""
    try:
        from ogscope.web.api.debug.services import DebugCameraService
        camera = DebugCameraService.get_camera_instance()
        if not camera or not camera.is_capturing:
            raise HTTPException(status_code=503, detail="相机未运行")

        import cv2
        import numpy as np

        boundary = "frame"

        async def frame_generator():
            while True:
                frame = camera.get_video_frame()
                if frame is None:
                    break
                ok, buf = cv2.imencode('.png', frame)
                if not ok:
                    continue
                data = buf.tobytes()
                yield (
                    b"--" + boundary.encode() + b"\r\n"
                    b"Content-Type: image/png\r\n"
                    b"Content-Length: " + str(len(data)).encode() + b"\r\n\r\n" + data + b"\r\n"
                )

        return StreamingResponse(frame_generator(), media_type=f"multipart/x-mixed-replace; boundary={boundary}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/stop")
async def stop_debug_camera():
    """停止调试相机"""
    try:
        return await DebugCameraService.stop_camera()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/rotation/{rotation}")
async def set_camera_rotation(rotation: int):
    """设置相机旋转角度"""
    try:
        from ogscope.web.api.debug.services import DebugCameraService
        result = await DebugCameraService.set_rotation(rotation)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/camera/preview")
async def get_debug_camera_preview():
    """获取调试相机预览"""
    try:
        return await DebugCameraService.get_preview()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/capture")
async def capture_debug_image():
    """拍摄单张图片"""
    try:
        return await DebugCameraService.capture_image()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/record/start")
async def start_debug_recording():
    """开始录制视频"""
    try:
        return await DebugCameraService.start_recording()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/record/stop")
async def stop_debug_recording():
    """停止录制视频"""
    try:
        return await DebugCameraService.stop_recording()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/size")
async def set_camera_size(width: int = Query(..., gt=0), height: int = Query(..., gt=0)):
    """仅切换分辨率（宽高），不影响当前帧率；必要时重启预览"""
    try:
        from ogscope.web.api.debug.services import DebugCameraService
        result = await DebugCameraService.set_size(width, height)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/sampling")
async def set_camera_sampling_mode(mode: str = Query(..., pattern="^(supersample|native|crop)$")):
    """设置采样模式：supersample | native | crop"""
    try:
        from ogscope.web.api.debug.services import DebugCameraService
        return await DebugCameraService.set_sampling_mode(mode)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/fps")
async def set_camera_fps(fps: int = Query(..., gt=0)):
    """仅设置帧率，尽量不影响当前预览"""
    try:
        from ogscope.web.api.debug.services import DebugCameraService
        return await DebugCameraService.set_fps(fps)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/debug/camera/settings")
async def update_debug_camera_settings(settings: CameraSettings):
    """更新调试相机设置"""
    try:
        return await DebugCameraService.update_settings(settings.dict())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/reset")
async def reset_debug_camera():
    """重置相机到默认设置"""
    try:
        return await DebugCameraService.reset_camera()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/noise-reduction")
async def set_noise_reduction(level: int = Query(..., ge=0, le=4)):
    """设置降噪级别 (0-4)"""
    try:
        return await DebugCameraService.set_noise_reduction(level)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/white-balance")
async def set_white_balance(
    mode: str = Query(..., pattern="^(auto|manual|night)$"),
    gain_r: float = Query(1.0, ge=0.1, le=3.0),
    gain_b: float = Query(1.0, ge=0.1, le=3.0)
):
    """设置白平衡模式"""
    try:
        return await DebugCameraService.set_white_balance(mode, gain_r, gain_b)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/image-enhancement")
async def set_image_enhancement(
    contrast: float = Query(1.0, ge=0.5, le=2.0),
    brightness: float = Query(0.0, ge=-1.0, le=1.0),
    saturation: float = Query(1.0, ge=0.0, le=2.0),
    sharpness: float = Query(1.0, ge=0.0, le=2.0)
):
    """设置图像增强参数"""
    try:
        return await DebugCameraService.set_image_enhancement(contrast, brightness, saturation, sharpness)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/night-mode")
async def set_night_mode(enabled: bool = Query(True)):
    """设置夜间模式"""
    try:
        return await DebugCameraService.set_night_mode(enabled)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/camera/image-quality")
async def get_image_quality():
    """获取图像质量指标"""
    try:
        return await DebugCameraService.get_image_quality()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/night-mode-preset")
async def apply_night_mode_preset():
    """应用夜间模式预设"""
    try:
        return await DebugCameraService.apply_night_mode_preset()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/backup-settings")
async def backup_camera_settings():
    """备份当前相机设置"""
    try:
        return await DebugCameraService.save_current_settings_backup()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/restore-settings")
async def restore_camera_settings():
    """从备份恢复相机设置"""
    try:
        return await DebugCameraService.restore_settings_backup()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/camera/verify-supersample")
async def verify_supersample_settings():
    """验证超采样设置的有效性"""
    try:
        from ogscope.web.api.debug.services import get_camera_instance
        
        camera = get_camera_instance()
        if not camera or not camera.is_initialized:
            raise HTTPException(status_code=500, detail="相机未初始化")
        
        # 获取相机详细信息
        info = camera.get_camera_info()
        
        # 验证超采样设置
        verification_result = {
            "sampling_mode": info.get('sampling_mode', 'unknown'),
            "capture_resolution": f"{info.get('capture_width', 0)}x{info.get('capture_height', 0)}",
            "output_resolution": f"{info.get('output_width', 0)}x{info.get('output_height', 0)}",
            "is_supersample_active": False,
            "supersample_ratio": 1.0,
            "verification_status": "unknown",
            "recommendations": []
        }
        
        # 检查超采样是否有效
        if info.get('sampling_mode') == 'supersample':
            capture_width = info.get('capture_width', 0)
            capture_height = info.get('capture_height', 0)
            output_width = info.get('output_width', 0)
            output_height = info.get('output_height', 0)
            
            if capture_width > 0 and capture_height > 0 and output_width > 0 and output_height > 0:
                verification_result["is_supersample_active"] = True
                
                # 计算超采样比例
                width_ratio = capture_width / output_width
                height_ratio = capture_height / output_height
                verification_result["supersample_ratio"] = min(width_ratio, height_ratio)
                
                # 验证状态
                if width_ratio >= 1.5 and height_ratio >= 1.5:
                    verification_result["verification_status"] = "excellent"
                elif width_ratio >= 1.2 and height_ratio >= 1.2:
                    verification_result["verification_status"] = "good"
                elif width_ratio > 1.0 and height_ratio > 1.0:
                    verification_result["verification_status"] = "moderate"
                else:
                    verification_result["verification_status"] = "poor"
                    verification_result["recommendations"].append("超采样比例过低，建议增加捕获分辨率或减少输出分辨率")
            else:
                verification_result["verification_status"] = "error"
                verification_result["recommendations"].append("无法获取有效的分辨率信息")
        else:
            verification_result["verification_status"] = "not_supersample"
            verification_result["recommendations"].append("当前不是超采样模式，请设置为 supersample 模式")
        
        # 添加详细建议
        if verification_result["sampling_mode"] == "supersample" and verification_result["is_supersample_active"]:
            if verification_result["supersample_ratio"] < 1.2:
                verification_result["recommendations"].append("超采样比例较低，图像质量提升有限")
            elif verification_result["supersample_ratio"] > 3.0:
                verification_result["recommendations"].append("超采样比例很高，可能影响性能，建议适当降低")
            
            verification_result["recommendations"].append("超采样设置正常，视频流将使用降采样后的高质量图像")
        
        return {
            "success": True,
            "verification": verification_result,
            "camera_info": info
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/test-image-size")
async def test_image_size():
    """测试捕获图像的实际尺寸，验证超采样是否生效"""
    try:
        from ogscope.web.api.debug.services import get_camera_instance
        
        camera = get_camera_instance()
        if not camera or not camera.is_initialized:
            raise HTTPException(status_code=500, detail="相机未初始化")
        
        # 捕获一张图像
        image = camera.capture_image()
        if image is None:
            raise HTTPException(status_code=500, detail="无法捕获图像")
        
        # 获取图像尺寸信息
        actual_height, actual_width = image.shape[:2]
        info = camera.get_camera_info()
        
        test_result = {
            "actual_image_size": f"{actual_width}x{actual_height}",
            "expected_output_size": f"{info.get('output_width', 0)}x{info.get('output_height', 0)}",
            "expected_capture_size": f"{info.get('capture_width', 0)}x{info.get('capture_height', 0)}",
            "sampling_mode": info.get('sampling_mode', 'unknown'),
            "size_match": False,
            "supersample_working": False,
            "analysis": ""
        }
        
        # 分析结果
        expected_width = info.get('output_width', 0)
        expected_height = info.get('output_height', 0)
        
        if actual_width == expected_width and actual_height == expected_height:
            test_result["size_match"] = True
            test_result["analysis"] = "图像尺寸与预期输出尺寸完全匹配"
            
            if info.get('sampling_mode') == 'supersample':
                capture_width = info.get('capture_width', 0)
                capture_height = info.get('capture_height', 0)
                if capture_width > expected_width and capture_height > expected_height:
                    test_result["supersample_working"] = True
                    test_result["analysis"] += "，超采样功能正常工作"
                else:
                    test_result["analysis"] += "，但超采样可能未正确配置"
        else:
            test_result["analysis"] = f"图像尺寸不匹配！实际: {actual_width}x{actual_height}, 预期: {expected_width}x{expected_height}"
        
        return {
            "success": True,
            "test_result": test_result,
            "camera_info": info
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 预设管理 ====================

@router.get("/debug/camera/presets")
async def get_camera_presets():
    """获取相机预设列表"""
    try:
        return await DebugPresetService.get_presets()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/presets")
async def save_camera_preset(preset: CameraPreset):
    """保存相机预设"""
    try:
        return await DebugPresetService.save_preset(preset.dict())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/presets/{preset_name}/apply")
async def apply_camera_preset(preset_name: str):
    """应用相机预设"""
    try:
        return await DebugPresetService.apply_preset(preset_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/debug/camera/presets/{preset_name}")
async def delete_camera_preset(preset_name: str):
    """删除相机预设"""
    try:
        return await DebugPresetService.delete_preset(preset_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 文件管理 ====================

@router.get("/debug/files")
async def get_capture_files():
    """获取拍摄文件列表"""
    try:
        return await DebugFileService.get_files()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/files/{filename}")
async def download_capture_file(filename: str):
    """下载拍摄文件"""
    from pathlib import Path
    DEBUG_CAPTURES_DIR = Path.home() / "dev_captures"
    file_path = DEBUG_CAPTURES_DIR / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/octet-stream"
    )


@router.get("/debug/files/{filename}/info")
async def get_file_info(filename: str):
    """获取文件信息"""
    try:
        return await DebugFileService.get_file_info(filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/debug/files/{filename}")
async def delete_capture_file(filename: str):
    """删除拍摄文件"""
    try:
        return await DebugFileService.delete_file(filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
