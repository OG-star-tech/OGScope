"""
素材分析路由 / Asset analysis routes
"""

import mimetypes

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse

from ogscope.web.api.analysis.services import analysis_service
from ogscope.web.api.models.schemas import (
    AnalysisBatchSolveRequest,
    AnalysisExperimentCreate,
    AnalysisExtractPreviewRequest,
    AnalysisJobCreateRequest,
    AnalysisPresetCreate,
    AnalysisSolveImageRequest,
    AnalysisSolveVideoFrameRequest,
    ImportFromDebugRequest,
)

router = APIRouter()


@router.get("/analysis/uploads")
async def list_analysis_uploads():
    """列出已上传素材（持久化目录）/ List persisted uploads"""
    try:
        return analysis_service.list_uploads()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@router.get("/analysis/uploads/{filename}/experiment_count")
async def upload_experiment_count(filename: str):
    """引用该素材的实验记录条数 / Count experiments for upload."""
    try:
        return analysis_service.upload_experiment_count(filename)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.delete("/analysis/uploads/{filename}")
async def delete_analysis_upload(
    filename: str,
    delete_experiments: bool = Query(
        False, description="同时删除引用该素材的实验记录 / Also delete linked experiments"
    ),
):
    """从素材池删除文件及侧车 / Delete file from pool and sidecar."""
    try:
        return analysis_service.delete_upload(filename, delete_experiments=delete_experiments)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/analysis/uploads/{filename}/info")
async def get_analysis_upload_file_info(filename: str):
    """上传素材侧车合并信息（与调试 info 形状对齐）/ Upload file + sidecar merged info."""
    try:
        return analysis_service.get_upload_file_info(filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/analysis/uploads/file")
async def get_analysis_upload_file(
    filename: str = Query(..., description="文件名 / Basename")
):
    """下载已上传文件（预览或复用）/ Serve persisted upload for preview or reuse"""
    try:
        path = analysis_service.resolve_upload_path(filename)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="文件不存在 / File not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    suffix = path.suffix.lower()
    media_map = {
        ".mp4": "video/mp4",
        ".m4v": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
        ".avi": "video/x-msvideo",
    }
    media = media_map.get(suffix)
    if not media:
        media, _ = mimetypes.guess_type(path.name)
    return FileResponse(
        path,
        media_type=media or "application/octet-stream",
        filename=path.name,
    )


@router.post("/analysis/upload")
async def upload_analysis_asset(
    file: UploadFile = File(...),
    source: str = Form(default="analysis_upload"),
):
    """上传素材 / Upload asset（可选来源标签 / optional source tag）"""
    try:
        payload = await file.read()
        return await analysis_service.save_upload(
            filename=file.filename or "uploaded.bin",
            payload=payload,
            source=source,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/analysis/uploads/import_from_debug")
async def import_upload_from_debug(body: ImportFromDebugRequest):
    """从调试采集目录复制到素材池 / Copy dev_captures file into analysis pool."""
    try:
        return analysis_service.import_from_debug_capture(body.filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
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


@router.post("/analysis/solve/batch")
async def solve_batch(body: AnalysisBatchSolveRequest):
    """同一素材多组参数批量解算 / Batch solve with multiple param sets."""
    try:
        return await analysis_service.batch_solve(body)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/analysis/presets")
async def list_analysis_presets(
    scope: str = Query("user", description="official | user")
):
    """列出预设 / List presets."""
    try:
        return analysis_service.list_presets(scope)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/analysis/presets")
async def create_analysis_preset(body: AnalysisPresetCreate):
    """创建用户预设 / Create user preset."""
    try:
        return analysis_service.create_user_preset(body)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/analysis/presets/{preset_id}")
async def delete_analysis_preset(preset_id: str):
    """删除用户预设 / Delete user preset."""
    try:
        analysis_service.delete_user_preset(preset_id)
        return {"success": True}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/analysis/experiments")
async def create_analysis_experiment(body: AnalysisExperimentCreate):
    """保存实验记录 / Save experiment record."""
    try:
        return analysis_service.create_experiment(body)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/analysis/experiments/{experiment_id}")
async def delete_analysis_experiment(experiment_id: str):
    """删除一条实验记录 / Delete one experiment record."""
    try:
        analysis_service.delete_experiment(experiment_id)
        return {"success": True}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/analysis/experiments")
async def list_analysis_experiments(
    q: str | None = Query(None, description="搜索文件名或预设名 / Search"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    """实验记录列表 / Experiment list."""
    try:
        return analysis_service.list_experiments(q, page, page_size)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/analysis/experiments/export")
async def export_analysis_experiments(
    export_format: str = Query("json", alias="format", description="json | csv"),
):
    """导出实验记录 / Export experiments."""
    try:
        text = analysis_service.export_experiments(export_format)
        media = (
            "application/json" if export_format == "json" else "text/csv; charset=utf-8"
        )
        return PlainTextResponse(content=text, media_type=media)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc




@router.get("/analysis/settings")
async def analysis_lab_settings():
    """分析台公开默认配置 / Public defaults for analysis lab."""
    try:
        return analysis_service.lab_public_settings()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/analysis/solve/frame")
async def solve_analysis_frame(body: AnalysisSolveVideoFrameRequest):
    """相机或视频单帧解算 / Solve one frame from camera or pool video."""
    try:
        return await analysis_service.solve_video_frame(body)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/analysis/experiments/{experiment_id}/asset")
async def get_experiment_asset_file(experiment_id: str):
    """实验素材快照（用于回放）/ Experiment asset snapshot for replay."""
    try:
        path = analysis_service.get_experiment_asset_path(experiment_id)
        media, _ = mimetypes.guess_type(path.name)
        return FileResponse(path, media_type=media or "application/octet-stream")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

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
