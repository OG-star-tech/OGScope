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
from ogscope.core.realtime import realtime_solve_service

router = APIRouter()


# ==================== 相机控制 ==================== / ==================== Camera Control ====================

@router.get("/debug/camera/status")
async def get_debug_camera_status():
    """获取调试相机状态 / Get debug camera status"""
    try:
        return await DebugCameraService.get_camera_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/start")
async def start_debug_camera():
    """启动调试相机 / Start the debug camera"""
    try:
        return await DebugCameraService.start_camera()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/camera/stream")
async def stream_debug_camera(quality: int = Query(70, ge=10, le=100)):
    """MJPEG 实时流 - 可配置压缩质量 / MJPEG live streaming - configurable compression quality"""
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
    """无损质量实时流 - 使用PNG格式展示超采样效果 / Lossless quality live streaming - using PNG format to demonstrate supersampling effects"""
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
    """停止调试相机 / Stop debugging camera"""
    try:
        return await DebugCameraService.stop_camera()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/rotation/{rotation}")
async def set_camera_rotation(rotation: int):
    """设置相机旋转角度 / Set camera rotation angle"""
    try:
        from ogscope.web.api.debug.services import DebugCameraService
        result = await DebugCameraService.set_rotation(rotation)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/camera/preview")
async def get_debug_camera_preview():
    """获取调试相机预览 / Get debug camera preview"""
    try:
        return await DebugCameraService.get_preview()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/capture")
async def capture_debug_image():
    """拍摄单张图片 / Take a single picture"""
    try:
        return await DebugCameraService.capture_image()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/record/start")
async def start_debug_recording():
    """开始录制视频 / Start recording video"""
    try:
        return await DebugCameraService.start_recording()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/record/stop")
async def stop_debug_recording():
    """停止录制视频 / Stop recording video"""
    try:
        return await DebugCameraService.stop_recording()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/size")
async def set_camera_size(width: int = Query(..., gt=0), height: int = Query(..., gt=0)):
    """仅切换分辨率（宽高），不影响当前帧率；必要时重启预览 / Only switches the resolution (width and height) and does not affect the current frame rate; restart the preview if necessary"""
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
    """仅设置帧率，尽量不影响当前预览 / Only set the frame rate and try not to affect the current preview"""
    try:
        from ogscope.web.api.debug.services import DebugCameraService
        return await DebugCameraService.set_fps(fps)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/debug/camera/settings")
async def update_debug_camera_settings(settings: CameraSettings):
    """更新调试相机设置 / Update debug camera settings"""
    try:
        return await DebugCameraService.update_settings(settings.dict())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/reset")
async def reset_debug_camera():
    """重置相机到默认设置 / Reset camera to default settings"""
    try:
        return await DebugCameraService.reset_camera()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/night-mode")
async def set_night_mode(enabled: bool = Query(True)):
    """设置夜间模式 / Set night mode"""
    try:
        return await DebugCameraService.set_night_mode(enabled)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/camera/image-quality")
async def get_image_quality():
    """获取图像质量指标 / Get image quality metrics"""
    try:
        return await DebugCameraService.get_image_quality()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/night-mode-preset")
async def apply_night_mode_preset():
    """应用夜间模式预设 / Apply night mode preset"""
    try:
        return await DebugCameraService.apply_night_mode_preset()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/backup-settings")
async def backup_camera_settings():
    """备份当前相机设置 / Back up current camera settings"""
    try:
        return await DebugCameraService.save_current_settings_backup()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/restore-settings")
async def restore_camera_settings():
    """从备份恢复相机设置 / Restore camera settings from backup"""
    try:
        return await DebugCameraService.restore_settings_backup()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/color-mode")
async def set_camera_color_mode(color_mode: str = Query(..., pattern="^(color|mono)$")):
    """设置相机颜色模式 / Set camera color mode"""
    try:
        return await DebugCameraService.set_color_mode(color_mode)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




# ==================== 预设管理 ==================== / ==================== Default Management ====================

@router.get("/debug/camera/presets")
async def get_camera_presets():
    """获取相机预设列表 / Get a list of camera presets"""
    try:
        return await DebugPresetService.get_presets()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/presets")
async def save_camera_preset(preset: CameraPreset):
    """保存相机预设 / Save camera presets"""
    try:
        return await DebugPresetService.save_preset(preset.dict())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/presets/{preset_name}/apply")
async def apply_camera_preset(preset_name: str):
    """应用相机预设 / Apply camera presets"""
    try:
        return await DebugPresetService.apply_preset(preset_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/debug/camera/presets/{preset_name}")
async def delete_camera_preset(preset_name: str):
    """删除相机预设 / Delete camera preset"""
    try:
        return await DebugPresetService.delete_preset(preset_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 文件管理 ==================== / ==================== File Management ====================

@router.get("/debug/files")
async def get_capture_files():
    """获取拍摄文件列表 / Get shooting file list"""
    try:
        return await DebugFileService.get_files()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/files/{filename}")
async def download_capture_file(filename: str):
    """下载拍摄文件 / Download shooting files"""
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
    """获取文件信息 / Get file information"""
    try:
        return await DebugFileService.get_file_info(filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/debug/files/{filename}")
async def delete_capture_file(filename: str):
    """删除拍摄文件 / Delete shooting files"""
    try:
        return await DebugFileService.delete_file(filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 实时解算 ==================== / ==================== Realtime Solving ====================


@router.post("/debug/analysis/realtime/start")
async def start_realtime_solving(
    hint_ra_deg: float | None = Query(default=None),
    hint_dec_deg: float | None = Query(default=None),
):
    """启动实时解算 / Start realtime solving"""
    try:
        return await realtime_solve_service.start(
            hint_ra_deg=hint_ra_deg, hint_dec_deg=hint_dec_deg
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/analysis/realtime/stop")
async def stop_realtime_solving():
    """停止实时解算 / Stop realtime solving"""
    try:
        return await realtime_solve_service.stop()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/analysis/realtime/status")
async def get_realtime_solving_status():
    """获取实时解算状态 / Get realtime solving status"""
    try:
        return await realtime_solve_service.get_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
