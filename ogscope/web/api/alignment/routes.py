"""
极轴校准相关API路由
"""
from fastapi import APIRouter
from ogscope.web.api.models.schemas import PolarAlignStatus, AlignmentStatus

router = APIRouter()


@router.post("/polar-align/start")
async def start_polar_alignment():
    """开始极轴校准 / Start polar alignment"""
    # TODO: 实现极轴校准启动 / TODO: Implement polar axis calibration startup
    return {
        "success": True,
        "message": "极轴校准已启动",
    }


@router.post("/alignment/start")
async def start_alignment():
    """开始极轴校准 / Start polar alignment"""
    # TODO: 实现极轴校准启动逻辑 / TODO: Implement polar axis calibration startup logic
    return {"status": "success", "message": "极轴校准已开始"}


@router.post("/alignment/stop")
async def stop_alignment():
    """停止极轴校准 / Stop polar calibration"""
    # TODO: 实现极轴校准停止逻辑 / TODO: Implement polar axis calibration stop logic
    return {"status": "success", "message": "极轴校准已停止"}


@router.get("/alignment/status")
async def get_alignment_status():
    """获取极轴校准状态 / Get polar calibration status"""
    # TODO: 实现极轴校准状态获取逻辑 / TODO: Implement polar axis calibration status acquisition logic
    return {
        "status": "running",
        "azimuth_error": 2.5,
        "altitude_error": 1.8,
        "precision": "good",
        "progress": 75
    }


@router.get("/polar-align/status")
async def get_polar_align_status() -> PolarAlignStatus:
    """获取极轴校准状态 / Get polar calibration status"""
    # TODO: 实现状态获取 / TODO: Implement status acquisition
    return PolarAlignStatus(
        is_running=False,
        progress=0.0,
        azimuth_error=0.0,
        altitude_error=0.0,
    )


@router.post("/polar-align/stop")
async def stop_polar_alignment():
    """停止极轴校准 / Stop polar calibration"""
    # TODO: 实现极轴校准停止 / TODO: Implement polar axis calibration stop
    return {
        "success": True,
        "message": "极轴校准已停止",
    }
