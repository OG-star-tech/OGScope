"""
OGScope Web API 主路由 / OGScope web API router.
整合所有 API 模块，并支持按运行角色裁剪 / Compose API modules with role-aware toggles.
"""

from fastapi import APIRouter

from ogscope.web.api.alignment.routes import router as alignment_router
from ogscope.web.api.analysis.routes import router as analysis_router
from ogscope.web.api.camera.routes import router as camera_router
from ogscope.web.api.core.routes import router as core_contract_router
from ogscope.web.api.debug.routes import router as debug_router
from ogscope.web.api.network.routes import router as network_router
from ogscope.web.api.system.routes import router as system_router


def create_api_router(
    *,
    include_network: bool = True,
    include_dev_debug: bool = True,
) -> APIRouter:
    """按角色构造 API 路由 / Build API router based on runtime role."""
    router = APIRouter()
    router.include_router(camera_router, tags=["Camera - 相机"])
    router.include_router(alignment_router, tags=["Alignment - 极轴校准"])
    if include_network:
        router.include_router(network_router, tags=["Network - 网络"])
    router.include_router(core_contract_router, tags=["Core - 标准契约"])
    router.include_router(
        system_router,
        prefix="/dev",
        tags=["Dev - 系统状态"],
    )
    if include_dev_debug:
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
    return router


# 默认导出保持向后兼容 / Keep default export for backward compatibility.
router = create_api_router()
