"""
调试控制台API路由
"""

import asyncio
import datetime as dt
import json
import logging
import os
import subprocess
import time

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from ogscope.config import get_settings
from ogscope.core.realtime import realtime_solve_service
from ogscope.web.api.debug.services import (
    DebugCameraService,
    DebugFileService,
    DebugPresetService,
)
from ogscope.web.api.models.schemas import (
    CameraMirrorBody,
    CameraPreset,
    CameraSettings,
)
from ogscope.web.mjpeg_stream_helpers import mjpeg_sleep_or_disconnect
from ogscope.web.mjpeg_stream_limiter import get_mjpeg_stream_limiter

logger = logging.getLogger(__name__)
router = APIRouter()

_MJPEG_LIMIT_DETAIL = (
    "MJPEG stream limit reached; close other previews or tabs / "
    "已达到 MJPEG 同时连接上限，请关闭其他标签页的预览"
)

_DEFAULT_PREVIEW_JPEG_QUALITY = int(os.getenv("OGSCOPE_PREVIEW_JPEG_QUALITY", "75"))
_PREVIEW_CLIENT_LAST_TS: dict[str, float] = {}
_DEBUG_PREVIEW_MIN_INTERVAL_SEC = max(
    0.0,
    float(os.getenv("OGSCOPE_DEBUG_PREVIEW_MIN_INTERVAL_MS", "150") or "150") / 1000.0,
)


def _journal_priority_to_level(priority: str | int | None) -> str:
    try:
        p = int(priority) if priority is not None else 6
    except (TypeError, ValueError):
        p = 6
    if p <= 3:
        return "ERROR"
    if p == 4:
        return "WARN"
    return "INFO"


def _read_journal_logs(
    service: str,
    since_seconds: int,
    limit: int,
) -> list[dict[str, str | int | None]]:
    cmd = [
        "journalctl",
        "--no-pager",
        "-o",
        "json",
        "-u",
        service,
        "--since",
        f"{since_seconds} seconds ago",
        "-n",
        str(limit),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "journalctl failed")
    rows: list[dict[str, str | int | None]] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = str(item.get("MESSAGE", "")).strip()
        if not msg:
            continue
        priority = item.get("PRIORITY")
        level = _journal_priority_to_level(priority)
        ts_iso: str | None = None
        rt = item.get("__REALTIME_TIMESTAMP")
        try:
            if rt is not None:
                ts = dt.datetime.fromtimestamp(
                    int(str(rt)) / 1_000_000, tz=dt.timezone.utc
                )
                ts_iso = ts.isoformat()
        except (ValueError, TypeError):
            ts_iso = None
        rows.append(
            {
                "ts": ts_iso,
                "level": level,
                "message": msg,
                "source": str(item.get("_SYSTEMD_UNIT", service)),
                "priority": int(priority) if str(priority).isdigit() else None,
            }
        )
    return rows


# ==================== 相机控制 ==================== / ==================== Camera Control ====================


@router.get("/debug/camera/status")
async def get_debug_camera_status():
    """获取调试相机状态 / Get debug camera status"""
    try:
        return await DebugCameraService.get_camera_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/camera/runtime-overrides")
async def get_debug_camera_runtime_overrides():
    """获取运行时预览参数覆盖 / Get runtime preview overrides"""
    try:
        return await DebugCameraService.get_runtime_overrides()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/runtime-overrides/reset")
async def reset_debug_camera_runtime_overrides():
    """重置运行时预览参数覆盖 / Reset runtime preview overrides"""
    try:
        return await DebugCameraService.clear_runtime_overrides()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/runtime-overrides/apply-defaults")
async def apply_debug_camera_runtime_overrides_as_defaults():
    """确认将运行时预览参数写为系统默认 / Apply runtime overrides as system defaults"""
    try:
        return await DebugCameraService.apply_runtime_overrides_as_defaults()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/start")
async def start_debug_camera():
    """启动调试相机 / Start the debug camera"""
    try:
        return await DebugCameraService.start_camera()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _streaming_response_debug_camera_mjpeg(
    request: Request,
    *,
    image_format: str,
    quality: int,
) -> StreamingResponse:
    """MJPEG 响应体：断连与单帧超时均可结束生成器并释放名额 / MJPEG body: disconnect or per-frame timeout ends generator and releases slot."""
    limiter = get_mjpeg_stream_limiter()
    if not await limiter.try_acquire():
        raise HTTPException(status_code=503, detail=_MJPEG_LIMIT_DETAIL)
    boundary = "frame"
    min_emit_interval = 1.0 / max(
        1, int(os.getenv("OGSCOPE_SHARED_PREVIEW_FPS", "8") or "8")
    )
    fetch_timeout_s = get_settings().stream_mjpeg_frame_fetch_timeout_ms / 1000.0
    ctype = "image/jpeg" if image_format.lower() == "jpeg" else "image/png"

    async def frame_generator():
        try:
            last_snap_frame_id = -1
            last_emit_mono = 0.0
            while True:
                if await request.is_disconnected():
                    break
                try:
                    code, data, snap_id = await asyncio.wait_for(
                        DebugCameraService.get_stream_frame_bytes(
                            image_format, quality, since_frame_id=last_snap_frame_id
                        ),
                        timeout=fetch_timeout_s,
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "MJPEG 单帧取流超时，结束响应以释放名额 / MJPEG frame fetch timed out, closing stream"
                    )
                    break
                if code == 304:
                    if not await mjpeg_sleep_or_disconnect(request, 0.03):
                        break
                    continue
                if code != 200 or data is None:
                    if not await mjpeg_sleep_or_disconnect(request, 0.05):
                        break
                    continue
                now = time.monotonic()
                wait = last_emit_mono + min_emit_interval - now
                if wait > 0:
                    if not await mjpeg_sleep_or_disconnect(request, wait):
                        break
                last_snap_frame_id = snap_id
                last_emit_mono = time.monotonic()
                yield (
                    b"--" + boundary.encode() + b"\r\n"
                    b"Content-Type: " + ctype.encode() + b"\r\n"
                    b"Content-Length: "
                    + str(len(data)).encode()
                    + b"\r\n\r\n"
                    + data
                    + b"\r\n"
                )
        finally:
            await limiter.release()

    return StreamingResponse(
        frame_generator(),
        media_type=f"multipart/x-mixed-replace; boundary={boundary}",
    )


@router.get("/debug/camera/stream")
async def stream_debug_camera(
    request: Request,
    quality: int = Query(_DEFAULT_PREVIEW_JPEG_QUALITY, ge=10, le=100),
):
    """MJPEG 实时流 - 可配置压缩质量 / MJPEG live streaming - configurable compression quality"""
    try:
        return await _streaming_response_debug_camera_mjpeg(
            request, image_format="jpeg", quality=quality
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/camera/stream-lossless")
async def stream_debug_camera_lossless(request: Request):
    """无损质量实时流 - 使用PNG格式展示超采样效果 / Lossless quality live streaming - using PNG format to demonstrate supersampling effects"""
    try:
        return await _streaming_response_debug_camera_mjpeg(
            request, image_format="png", quality=100
        )
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


@router.post("/debug/camera/mirror")
async def set_camera_mirror(body: CameraMirrorBody):
    """设置相机输出水平/垂直镜像 / Set camera output horizontal and vertical mirror"""
    try:
        result = await DebugCameraService.set_mirror(
            body.flip_horizontal, body.flip_vertical
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/camera/preview")
async def get_debug_camera_preview(
    request: Request,
    since_frame_id: int | None = Query(default=None),
):
    """获取调试相机预览 / Get debug camera preview"""
    try:
        if _DEBUG_PREVIEW_MIN_INTERVAL_SEC > 0:
            client_host = request.client.host if request.client else "unknown"
            now = time.monotonic()
            last = _PREVIEW_CLIENT_LAST_TS.get(client_host, 0.0)
            if now - last < _DEBUG_PREVIEW_MIN_INTERVAL_SEC:
                return Response(status_code=304)
            _PREVIEW_CLIENT_LAST_TS[client_host] = now
        return await DebugCameraService.get_preview(since_frame_id=since_frame_id)
    except HTTPException:
        raise
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
async def set_camera_size(
    width: int = Query(..., gt=0), height: int = Query(..., gt=0)
):
    """仅切换分辨率（宽高），不影响当前帧率；必要时重启预览 / Only switches the resolution (width and height) and does not affect the current frame rate; restart the preview if necessary"""
    try:
        from ogscope.web.api.debug.services import DebugCameraService

        result = await DebugCameraService.set_size(width, height)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/sampling")
async def set_camera_sampling_mode(
    mode: str = Query(..., pattern="^(supersample|native|crop)$")
):
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
        return await DebugCameraService.update_settings(settings.model_dump())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/camera/auto-exposure")
async def set_debug_camera_auto_exposure(enabled: bool = Query(...)):
    """仅切换自动曝光模式 / Toggle auto-exposure mode only"""
    try:
        return await DebugCameraService.set_auto_exposure_mode(enabled)
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


@router.post("/debug/camera/white-balance")
async def set_camera_white_balance(
    mode: str = Query(..., pattern="^(auto|manual|night)$"),
    gain_r: float = Query(1.0, ge=0.1, le=3.0),
    gain_b: float = Query(1.0, ge=0.1, le=3.0),
):
    """设置白平衡模式 / Set white balance mode"""
    try:
        return await DebugCameraService.set_white_balance(mode, gain_r, gain_b)
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
        return await DebugPresetService.save_preset(preset.model_dump())
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
        path=str(file_path), filename=filename, media_type="application/octet-stream"
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


# ==================== 系统日志 ==================== / ==================== System Logs ====================


@router.get("/debug/logs/systemd")
async def get_systemd_logs(
    service: str = Query(default="ogscope"),
    since_seconds: int = Query(default=600, ge=10, le=86400),
    limit: int = Query(default=120, ge=10, le=1000),
    levels: str = Query(default="INFO,WARN,ERROR"),
):
    """读取 systemd/journalctl 日志 / Read systemd journal logs."""
    level_set = {
        part.strip().upper()
        for part in levels.split(",")
        if part.strip().upper() in {"INFO", "WARN", "ERROR"}
    }
    if not level_set:
        level_set = {"INFO", "WARN", "ERROR"}
    try:
        rows = await asyncio.to_thread(
            _read_journal_logs,
            service,
            since_seconds,
            limit,
        )
        filtered = [row for row in rows if str(row.get("level")) in level_set]
        return {
            "service": service,
            "since_seconds": since_seconds,
            "limit": limit,
            "levels": sorted(level_set),
            "items": filtered,
            "count": len(filtered),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 实时解算 ==================== / ==================== Realtime Solving ====================


@router.post("/debug/analysis/realtime/start")
async def start_realtime_solving(
    hint_ra_deg: float | None = Query(default=None),
    hint_dec_deg: float | None = Query(default=None),
    fov_estimate: float | None = Query(default=None),
    fov_max_error: float | None = Query(default=None),
    solve_timeout_ms: int | None = Query(default=None),
):
    """启动实时解算 / Start realtime solving"""
    try:
        return await realtime_solve_service.start(
            hint_ra_deg=hint_ra_deg,
            hint_dec_deg=hint_dec_deg,
            fov_estimate=fov_estimate,
            fov_max_error=fov_max_error,
            solve_timeout_ms=solve_timeout_ms,
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
