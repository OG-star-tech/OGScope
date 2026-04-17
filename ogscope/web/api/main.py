"""
OGScope Web API 主路由
整合所有API模块
"""

from fastapi import APIRouter

from ogscope.core.capabilities import detect_capabilities
from ogscope.web.api.core.routes import router as core_contract_router
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
router.include_router(network_router, tags=["Network - 网络"])
router.include_router(core_contract_router, tags=["Core - 标准契约"])
router.include_router(
    system_router,
    prefix="/dev",
    tags=["Dev - 系统状态"],
)
router.include_router(
    debug_router,
    prefix="/dev",
    tags=["Dev - 调试工具"],
)
router.include_router(
    analysis_router,
    prefix="/dev",
    tags=["Dev - 分析实验"],
)

# legacy hardware protocol 为可选能力（迁移至 external integrator 后可不存在）/ legacy hardware protocol is optional and may move to external integrator.
if detect_capabilities().legacy protocol_i2c:
    from ogscope.web.api.legacy protocol.routes import router as legacy protocol_router

    router.include_router(legacy protocol_router, tags=["legacy hardware protocol - 赤道仪控制"])
