"""
Core v1 标准契约路由 / Core v1 standard contract routes.
"""

import asyncio
import logging
import os
import time
from pathlib import PurePath

from fastapi import APIRouter, HTTPException
from fastapi import Query
from fastapi.responses import StreamingResponse
from starlette.requests import Request

from ogscope.core.application import core_contract_service
from ogscope.config import get_settings
from ogscope.web.api.debug.services import DebugCameraService
from ogscope.web.api.models.schemas import (
    CoreAnalysisControlResponse,
    CoreAnalysisResultResponse,
    CoreCameraControlResponse,
    CoreCameraStatusResponse,
    CoreCameraTuneRequest,
    CoreStartAnalysisRequest,
    CoreStreamStatusResponse,
    CoreSystemStatusResponse,
    CoreVideoDetailResponse,
    CoreVideoListResponse,
)
from ogscope.web.mjpeg_stream_helpers import mjpeg_sleep_or_disconnect
from ogscope.web.mjpeg_stream_limiter import get_mjpeg_stream_limiter

router = APIRouter()
logger = logging.getLogger(__name__)
_MJPEG_LIMIT_DETAIL = "mjpeg_stream_limit_reached"
_DEFAULT_PREVIEW_JPEG_QUALITY = 75


def _validate_capture_filename(filename: str) -> str:
    """仅允许相对 basename 文件名 / Allow basename-only capture filename."""
    safe_name = PurePath(filename).name
    if not safe_name or safe_name != filename or safe_name in {".", ".."}:
        raise ValueError("invalid filename")
    if "/" in safe_name or "\\" in safe_name:
        raise ValueError("invalid filename")
    return safe_name


@router.post(
    "/core/v1/analysis/start",
    response_model=CoreAnalysisControlResponse,
)
async def core_start_analysis(body: CoreStartAnalysisRequest) -> CoreAnalysisControlResponse:
    """开始分析（Core 标准契约）/ Start analysis (Core contract)."""
    try:
        data = await core_contract_service.start_analysis(
            hint_ra_deg=body.hint_ra_deg,
            hint_dec_deg=body.hint_dec_deg,
            fov_estimate=body.fov_estimate,
            fov_max_error=body.fov_max_error,
            solve_timeout_ms=body.solve_timeout_ms,
        )
        return CoreAnalysisControlResponse(**data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/core/v1/analysis/result",
    response_model=CoreAnalysisResultResponse,
)
async def core_get_analysis_result() -> CoreAnalysisResultResponse:
    """获取分析结果（Core 标准契约）/ Get analysis result (Core contract)."""
    try:
        data = await core_contract_service.get_analysis_result()
        return CoreAnalysisResultResponse(**data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/core/v1/analysis/stop",
    response_model=CoreAnalysisControlResponse,
)
async def core_stop_analysis() -> CoreAnalysisControlResponse:
    """结束分析（Core 标准契约）/ Stop analysis (Core contract)."""
    try:
        data = await core_contract_service.stop_analysis()
        return CoreAnalysisControlResponse(**data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/core/v1/system/status",
    response_model=CoreSystemStatusResponse,
)
async def core_system_status() -> CoreSystemStatusResponse:
    """系统状态（Core 标准契约）/ System status (Core contract)."""
    try:
        data = await core_contract_service.get_system_status()
        return CoreSystemStatusResponse(**data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/core/v1/camera/status", response_model=CoreCameraStatusResponse)
async def core_camera_status() -> CoreCameraStatusResponse:
    """相机状态（Core 标准契约）/ Camera status (Core contract)."""
    try:
        data = await core_contract_service.get_camera_status()
        return CoreCameraStatusResponse(**data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/core/v1/camera/start", response_model=CoreCameraControlResponse)
async def core_camera_start() -> CoreCameraControlResponse:
    """启动相机（Core 标准契约）/ Start camera (Core contract)."""
    try:
        data = await core_contract_service.start_camera()
        return CoreCameraControlResponse(**data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/core/v1/camera/stop", response_model=CoreCameraControlResponse)
async def core_camera_stop() -> CoreCameraControlResponse:
    """停止相机（Core 标准契约）/ Stop camera (Core contract)."""
    try:
        data = await core_contract_service.stop_camera()
        return CoreCameraControlResponse(**data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/core/v1/camera/tune", response_model=CoreCameraControlResponse)
async def core_camera_tune(payload: CoreCameraTuneRequest) -> CoreCameraControlResponse:
    """微调相机参数（Core 标准契约）/ Tune camera settings (Core contract)."""
    try:
        data = await core_contract_service.tune_camera(payload.model_dump(exclude_none=True))
        return CoreCameraControlResponse(**data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/core/v1/camera/preview")
async def core_camera_preview(
    since_frame_id: int | None = Query(default=None),
):
    """获取单帧预览（JPEG）/ Fetch single preview frame (JPEG)."""
    try:
        return await DebugCameraService.get_preview(since_frame_id=since_frame_id)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def _streaming_response_core_camera_mjpeg(
    request: Request,
    *,
    image_format: str,
    quality: int,
) -> StreamingResponse:
    limiter = get_mjpeg_stream_limiter()
    if not await limiter.try_acquire():
        raise HTTPException(status_code=503, detail=_MJPEG_LIMIT_DETAIL)
    boundary = "frame"
    min_emit_interval = 1.0 / max(
        1, int(os.getenv("OGSCOPE_SHARED_PREVIEW_FPS", "8") or "8")
    )
    fetch_timeout_s = get_settings().stream_mjpeg_frame_fetch_timeout_ms / 1000.0
    content_type = "image/jpeg" if image_format.lower() == "jpeg" else "image/png"

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
                    logger.warning("core mjpeg frame fetch timeout, closing stream")
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
                if wait > 0 and not await mjpeg_sleep_or_disconnect(request, wait):
                    break
                last_snap_frame_id = snap_id
                last_emit_mono = time.monotonic()
                yield (
                    b"--"
                    + boundary.encode()
                    + b"\r\n"
                    + b"Content-Type: "
                    + content_type.encode()
                    + b"\r\n"
                    + b"Content-Length: "
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


@router.get("/core/v1/camera/stream")
async def core_camera_stream(
    request: Request,
    quality: int = Query(_DEFAULT_PREVIEW_JPEG_QUALITY, ge=10, le=100),
):
    """MJPEG 实时流（压缩）/ MJPEG live stream (compressed)."""
    try:
        return await _streaming_response_core_camera_mjpeg(
            request, image_format="jpeg", quality=quality
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/core/v1/camera/stream-lossless")
async def core_camera_stream_lossless(request: Request):
    """MJPEG 实时流（无损）/ MJPEG live stream (lossless)."""
    try:
        return await _streaming_response_core_camera_mjpeg(
            request, image_format="png", quality=100
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/core/v1/camera/stream/status", response_model=CoreStreamStatusResponse)
async def core_camera_stream_status() -> CoreStreamStatusResponse:
    """流控状态（Core 标准契约）/ Stream limiter status (Core contract)."""
    try:
        data = await core_contract_service.get_stream_status()
        return CoreStreamStatusResponse(**data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/core/v1/camera/videos", response_model=CoreVideoListResponse)
async def core_camera_videos() -> CoreVideoListResponse:
    """录制视频列表（Core 标准契约）/ Recorded videos list (Core contract)."""
    try:
        return CoreVideoListResponse(**(await core_contract_service.list_video_files()))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/core/v1/camera/videos/{filename}", response_model=CoreVideoDetailResponse)
async def core_camera_video_info(filename: str) -> CoreVideoDetailResponse:
    """录制视频详情（Core 标准契约）/ Recorded video detail (Core contract)."""
    try:
        safe_name = _validate_capture_filename(filename)
        return CoreVideoDetailResponse(
            **(await core_contract_service.get_video_file_info(safe_name))
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
