"""
素材分析路由 / Asset analysis routes
"""

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi import Query

from ogscope.web.api.analysis.services import analysis_service
from ogscope.web.api.models.schemas import AnalysisJobCreateRequest

router = APIRouter()


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
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/analysis/solve/image")
async def solve_single_image(
    input_name: str = Query(...),
    hint_ra_deg: float | None = Query(default=None),
    hint_dec_deg: float | None = Query(default=None),
):
    """直接解算单图 / Solve single image directly"""
    try:
        return await analysis_service.solve_single_image(
            input_name=input_name,
            hint_ra_deg=hint_ra_deg,
            hint_dec_deg=hint_dec_deg,
        )
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
