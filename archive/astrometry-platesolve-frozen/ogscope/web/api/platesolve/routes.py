"""
板块求解 API 路由 / Plate solve API routes

提供通过实时预览或上传文件进行板块求解的接口。
Provides endpoints for plate solving via live preview or uploaded files.
"""
import asyncio
import base64
import io
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from loguru import logger

from ogscope.algorithms.plate_solver import PlateSolver, SolveOptions
from ogscope.web.api.models.schemas import PlateSolveRequest, PlateSolveResponse

router = APIRouter()

# 全局求解器实例 (延迟初始化) / Global solver instance (lazy init)
_solver: Optional[PlateSolver] = None


def _get_solver() -> PlateSolver:
    """获取或创建求解器实例 / Get or create solver instance"""
    global _solver
    if _solver is None:
        from ogscope.config import get_settings

        settings = get_settings()
        _solver = PlateSolver(
            default_fov_estimate=getattr(settings, "platesolve_fov_estimate", None),
            default_fov_max_error=getattr(settings, "platesolve_fov_max_error", None),
            cache_dir=getattr(settings, "platesolve_cache_dir", None),
        )
    return _solver


def _request_to_options(req: PlateSolveRequest) -> SolveOptions:
    """将请求参数转换为求解选项 / Convert request params to solve options"""
    return SolveOptions(
        fov_estimate=req.fov_estimate,
        fov_max_error=req.fov_max_error,
        detection_sigma=req.detection_sigma,
        max_stars=req.max_stars,
        min_area=req.min_area,
        max_area=req.max_area,
        draw_overlay=req.draw_overlay,
    )


def _result_to_response(result) -> PlateSolveResponse:
    """将求解结果转换为 API 响应 / Convert solve result to API response"""
    d = result.to_dict()
    # 将叠加层图像转为 base64 / Encode annotated image as base64
    if result.annotated_image is not None:
        d["annotated_image_base64"] = base64.b64encode(result.annotated_image).decode("ascii")
    return PlateSolveResponse(**d)


@router.get("/platesolve/status")
async def get_platesolve_status():
    """获取板块求解器状态 / Get plate solver status"""
    solver = _get_solver()
    return {
        "available": solver.is_available,
        "initialized": solver.is_initialized,
    }


@router.post("/platesolve/preview", response_model=PlateSolveResponse)
async def solve_from_preview(request: PlateSolveRequest = PlateSolveRequest()):
    """从当前相机预览图进行板块求解 / Plate solve from current camera preview

    获取相机最新帧并进行板块求解，返回图像中心的天球坐标。
    Gets the latest camera frame and performs plate solving,
    returning the celestial coordinates of the image center.
    """
    solver = _get_solver()
    if not solver.is_available:
        raise HTTPException(
            status_code=503,
            detail="astrometry 未安装 / astrometry not installed",
        )

    # 获取当前预览帧 / Get current preview frame
    frame_data = await _get_current_frame()
    if frame_data is None:
        raise HTTPException(
            status_code=404,
            detail="无可用的相机帧 / No camera frame available",
        )

    options = _request_to_options(request)
    # 在线程池中运行以避免阻塞 / Run in thread pool to avoid blocking
    result = await asyncio.to_thread(solver.solve_bytes, frame_data, options)
    return _result_to_response(result)


@router.post("/platesolve/upload", response_model=PlateSolveResponse)
async def solve_from_upload(
    file: UploadFile = File(...),
    fov_estimate: Optional[float] = Query(None, description="视场角估计 (度) / FOV estimate (degrees)"),
    fov_max_error: Optional[float] = Query(None, description="视场角误差 (度) / FOV max error (degrees)"),
    draw_overlay: bool = Query(False, description="绘制叠加层 / Draw overlay on image"),
):
    """上传图像进行板块求解 / Upload image for plate solving

    支持 JPEG/PNG 格式，返回图像中心的天球坐标。
    Supports JPEG/PNG format, returns celestial coordinates of image center.
    """
    solver = _get_solver()
    if not solver.is_available:
        raise HTTPException(
            status_code=503,
            detail="astrometry 未安装 / astrometry not installed",
        )

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=400,
            detail="空文件 / Empty file",
        )

    options = SolveOptions(
        fov_estimate=fov_estimate,
        fov_max_error=fov_max_error,
        draw_overlay=draw_overlay,
    )
    # 在线程池中运行以避免阻塞 / Run in thread pool to avoid blocking
    result = await asyncio.to_thread(solver.solve_bytes, content, options)
    return _result_to_response(result)


@router.post("/platesolve/upload/image")
async def solve_from_upload_image(
    file: UploadFile = File(...),
    fov_estimate: Optional[float] = Query(None, description="视场角估计 (度) / FOV estimate (degrees)"),
    fov_max_error: Optional[float] = Query(None, description="视场角误差 (度) / FOV max error (degrees)"),
):
    """上传图像进行板块求解，返回带叠加层的 JPEG 图像 /
    Upload image for plate solving, returns annotated JPEG image

    直接返回标注后的图像，适合嵌入 <img> 标签。
    Returns annotated image directly, suitable for embedding in <img> tags.
    """
    solver = _get_solver()
    if not solver.is_available:
        raise HTTPException(status_code=503, detail="astrometry 未安装 / astrometry not installed")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="空文件 / Empty file")

    options = SolveOptions(
        fov_estimate=fov_estimate,
        fov_max_error=fov_max_error,
        draw_overlay=True,
    )
    # 在线程池中运行以避免阻塞 / Run in thread pool to avoid blocking
    result = await asyncio.to_thread(solver.solve_bytes, content, options)

    if result.annotated_image is None:
        raise HTTPException(status_code=500, detail="叠加层生成失败 / Overlay generation failed")

    return Response(content=result.annotated_image, media_type="image/jpeg")


@router.post("/platesolve/file", response_model=PlateSolveResponse)
async def solve_from_file(
    file_path: str = Query(..., description="图像文件路径 / Image file path"),
    fov_estimate: Optional[float] = Query(None, description="视场角估计 (度) / FOV estimate (degrees)"),
    fov_max_error: Optional[float] = Query(None, description="视场角误差 (度) / FOV max error (degrees)"),
    draw_overlay: bool = Query(False, description="绘制叠加层 / Draw overlay on image"),
):
    """从本地文件进行板块求解 / Plate solve from local file

    指定服务器上的图像文件路径进行求解。
    Specify an image file path on the server for solving.
    """
    solver = _get_solver()
    if not solver.is_available:
        raise HTTPException(
            status_code=503,
            detail="astrometry 未安装 / astrometry not installed",
        )

    # 安全检查: 只允许访问特定目录 / Security: restrict to allowed directories
    allowed_dirs = _get_allowed_dirs()
    resolved = Path(file_path).resolve()
    if not any(str(resolved).startswith(str(d)) for d in allowed_dirs):
        raise HTTPException(
            status_code=403,
            detail="不允许访问该路径 / Access to this path is not allowed",
        )

    options = SolveOptions(
        fov_estimate=fov_estimate,
        fov_max_error=fov_max_error,
        draw_overlay=draw_overlay,
    )
    # 在线程池中运行以避免阻塞 / Run in thread pool to avoid blocking
    result = await asyncio.to_thread(solver.solve_file, resolved, options)
    return _result_to_response(result)


def _get_allowed_dirs() -> list[Path]:
    """获取允许的文件访问目录 / Get allowed file access directories"""
    from ogscope.config import get_settings

    settings = get_settings()
    dirs = [
        Path(settings.data_dir).resolve(),
        Path(settings.upload_dir).resolve(),
        (Path.home() / "dev_captures").resolve(),
    ]
    # 测试图像目录 / Test images directory
    test_images = Path(__file__).resolve().parents[4] / "tests" / "images"
    if test_images.exists():
        dirs.append(test_images.resolve())
    return dirs


async def _get_current_frame() -> Optional[bytes]:
    """获取当前相机帧 / Get current camera frame

    尝试从调试服务或相机路由获取最新的 JPEG 帧。
    Tries to get the latest JPEG frame from debug service or camera routes.
    """
    # 优先从 debug 服务的缓存帧获取 / Prefer debug service cached frame
    try:
        from ogscope.web.api.debug.services import latest_preview_jpeg

        if latest_preview_jpeg is not None:
            return latest_preview_jpeg
    except ImportError:
        pass

    # 回退：尝试直接从相机获取 / Fallback: try camera directly
    try:
        from ogscope.web.api.camera.routes import (
            _camera_instance,
            _simulation_mode,
            _virtual_stream,
        )

        if _simulation_mode:
            return _virtual_stream.generate_frame()

        if _camera_instance is not None:
            import cv2

            frame = _camera_instance.get_video_frame()
            if frame is not None:
                _, jpeg_data = cv2.imencode(
                    ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90]
                )
                return jpeg_data.tobytes()
    except (ImportError, Exception) as e:
        logger.warning(f"获取相机帧失败: {e} / Failed to get camera frame: {e}")

    return None
