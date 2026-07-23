"""
Core v1 标准契约路由 / Core v1 standard contract routes.
"""

from fastapi import APIRouter, HTTPException

from ogscope.core.application import core_contract_service
from ogscope.domain.shared.filesystem import ensure_safe_basename
from ogscope.web.api.models.schemas import (
    CoreAnalysisControlResponse,
    CoreAnalysisResultResponse,
    CoreCameraControlResponse,
    CoreCameraStatusResponse,
    CoreCameraTuneRequest,
    CoreStartAnalysisRequest,
    CoreSystemStatusResponse,
    CoreVideoDetailResponse,
    CoreVideoListResponse,
)

router = APIRouter()


@router.post(
    "/core/v1/analysis/start",
    response_model=CoreAnalysisControlResponse,
)
async def core_start_analysis(
    body: CoreStartAnalysisRequest,
) -> CoreAnalysisControlResponse:
    """开始分析（Core 标准契约）/ Start analysis (Core contract)."""
    try:
        data = await core_contract_service.start_analysis(
            hint_ra_deg=body.hint_ra_deg,
            hint_dec_deg=body.hint_dec_deg,
            fov_estimate=body.fov_estimate,
            fov_max_error=body.fov_max_error,
            solve_timeout_ms=body.solve_timeout_ms,
            solve_context=body.solve_context,
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
        data = await core_contract_service.tune_camera(
            payload.model_dump(exclude_none=True)
        )
        return CoreCameraControlResponse(**data)
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
        safe_name = ensure_safe_basename(filename)
        return CoreVideoDetailResponse(
            **(await core_contract_service.get_video_file_info(safe_name))
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
