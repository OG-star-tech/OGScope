"""
OGScope Web API 主路由
整合所有API模块
"""

from fastapi import APIRouter

from ogscope.web.api.alignment.routes import router as alignment_router
from ogscope.web.api.analysis.routes import router as analysis_router
from ogscope.web.api.camera.routes import router as camera_router
from ogscope.web.api.debug.routes import router as debug_router
from ogscope.web.api.network.routes import router as network_router
from ogscope.web.api.system.routes import router as system_router

# 创建主路由器 / Create the main router
router = APIRouter()

# 注册各个模块的路由（含分组标签）/ Register routes for each module (with group tags)
router.include_router(camera_router, tags=["Camera - 相机"])
router.include_router(alignment_router, tags=["Alignment - 极轴校准"])
router.include_router(system_router, tags=["System - 系统"])
router.include_router(network_router, tags=["Network - 网络"])
router.include_router(debug_router, tags=["Debug - 调试"])
router.include_router(analysis_router, tags=["Analysis - 分析"])
