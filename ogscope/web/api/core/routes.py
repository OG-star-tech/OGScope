"""
Core v1 标准契约路由 / Core v1 standard contract routes.
"""

from fastapi import APIRouter, HTTPException

from ogscope.core.application import core_contract_service
from ogscope.web.api.models.schemas import (
    CoreAnalysisControlResponse,
    CoreAnalysisResultResponse,
    CoreStartAnalysisRequest,
    CoreSystemStatusResponse,
)

router = APIRouter()


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
