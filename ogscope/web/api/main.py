"""
OGScope Web API 主路由
整合所有API模块
"""
from fastapi import APIRouter
from ogscope.web.api.camera.routes import router as camera_router
from ogscope.web.api.alignment.routes import router as alignment_router
from ogscope.web.api.system.routes import router as system_router
from ogscope.web.api.debug.routes import router as debug_router

# 创建主路由器
router = APIRouter()

# 注册各个模块的路由
router.include_router(camera_router)
router.include_router(alignment_router)
router.include_router(system_router)
router.include_router(debug_router)


@router.get("/api")
async def api_root():
    """API根路径"""
    return {
        "name": "OGScope API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "modules": {
            "camera": "相机控制API",
            "alignment": "极轴校准API", 
            "system": "系统信息API",
            "debug": "调试控制台API"
        },
        "endpoints": {
            "camera": "/api/camera/",
            "alignment": "/api/alignment/",
            "system": "/api/system/",
            "debug": "/api/debug/"
        }
    }
