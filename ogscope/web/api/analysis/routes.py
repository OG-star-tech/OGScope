"""
素材分析路由 / Asset analysis routes
"""

import mimetypes

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from ogscope.web.api.analysis.services import analysis_service
from ogscope.web.api.models.schemas import (
    AnalysisExtractPreviewRequest,
    AnalysisJobCreateRequest,
    AnalysisSolveImageRequest,
)

router = APIRouter()


@router.get("/analysis/uploads")
async def list_analysis_uploads():
    """列出已上传素材（持久化目录）/ List persisted uploads"""
    try:
        return analysis_service.list_uploads()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/analysis/uploads/file")
async def get_analysis_upload_file(filename: str = Query(..., description="文件名 / Basename")):
    """下载已上传文件（预览或复用）/ Serve persisted upload for preview or reuse"""
    try:
        path = analysis_service.resolve_upload_path(filename)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="文件不存在 / File not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    media, _ = mimetypes.guess_type(path.name)
    return FileResponse(
        path,
        media_type=media or "application/octet-stream",
        filename=path.name,
    )


@router.post("/analysis/upload")
async def upload_analysis_asset(file: UploadFile = File(...)):
    """上传素材 / Upload asset"""
    try:
        payload = await file.read()
        return await analysis_service.save_upload(
            filename=file.filename or "uploaded.bin",
            payload=payload,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/analysis/jobs")
async def create_analysis_job(payload: AnalysisJobCreateRequest):
    """创建任务 / Create analysis job"""
    try:
        return await analysis_service.create_job(
            input_name=payload.input_name,
            input_type=payload.input_type,
            hint_ra_deg=payload.hint_ra_deg,
            hint_dec_deg=payload.hint_dec_deg,
            frame_step=payload.frame_step,
            max_frames=payload.max_frames,
            fov_estimate=payload.fov_estimate,
            fov_max_error=payload.fov_max_error,
            solve_timeout_ms=payload.solve_timeout_ms,
            centroid=payload.centroid,
            max_image_side=payload.max_image_side,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/analysis/solve/image")
async def solve_single_image(body: AnalysisSolveImageRequest):
    """直接解算单图（JSON body）/ Solve single image via JSON body."""
    try:
        return await analysis_service.solve_single_image(body)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/analysis/extract/preview")
async def extract_centroid_preview(body: AnalysisExtractPreviewRequest):
    """提星二值掩膜预览（不调解算）/ Preview centroid binary mask without plate solve."""
    try:
        return await analysis_service.extract_preview(body)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/analysis/jobs/{job_id}")
async def get_analysis_job(job_id: str):
    """查询任务状态 / Query job status"""
    try:
        return await analysis_service.get_job_status(job_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/analysis/jobs/{job_id}/result")
async def get_analysis_result(job_id: str):
    """查询任务结果 / Query job result"""
    try:
        return await analysis_service.get_job_result(job_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=str(exc)) from exc
