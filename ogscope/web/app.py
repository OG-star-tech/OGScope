"""
FastAPI Web 应用
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from ogscope.__version__ import __version__
from ogscope.config import get_settings
from ogscope.web.api.main import router as api_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """应用生命周期管理 / Application life cycle management"""
    # 启动时执行 / Execute at startup
    logger.info("初始化 Web 应用...")

    # 真实硬件下后台预热相机：不阻塞 Uvicorn 就绪；首次请求仍可在锁内完成初始化
    # Background warm-up on real hardware: do not block server readiness; first request can still init under lock.
    async def _warm_camera() -> None:
        try:
            from ogscope.utils.environment import should_use_simulation_mode

            if not should_use_simulation_mode():
                from ogscope.web.camera_shared import get_camera_manager

                await get_camera_manager().ensure_started()
                logger.info(
                    "相机已启动并进入共享预览缓存 / Camera streaming (shared preview cache)"
                )
        except Exception as e:
            logger.warning(
                f"启动时相机预热失败，将在首次请求时重试 / Camera warm-up failed, retry on demand: {e}"
            )

    async def _warm_solver() -> None:
        try:
            from ogscope.algorithms.plate_solve.solver import warmup_tetra3

            await asyncio.to_thread(warmup_tetra3)
            logger.info("解算器已预热 / Plate solver warmed up")
        except Exception as e:
            logger.warning(
                f"启动时解算器预热失败，将在首次解算时重试 / Solver warm-up failed, retry on first solve: {e}"
            )

    asyncio.create_task(_warm_camera())
    # 解算器预热改为启动阶段阻塞完成，避免首个解算请求与后台预热竞态导致“第一次明显变慢”
    # Warm the solver synchronously during startup to avoid first-request cold-start race.
    await _warm_solver()

    try:
        from ogscope.hardware.wifi_emergency_gpio import wifi_emergency_gpio_monitor

        wifi_emergency_gpio_monitor.start()
    except Exception as e:
        logger.warning("应急 GPIO 启动失败 / Emergency GPIO start failed: {}", e)

    yield

    # 关闭时执行 / Execute on shutdown
    logger.info("清理资源...")
    try:
        from ogscope.hardware.wifi_emergency_gpio import wifi_emergency_gpio_monitor

        wifi_emergency_gpio_monitor.stop()
    except Exception as e:
        logger.warning("应急 GPIO 停止异常 / Emergency GPIO stop error: {}", e)
    try:
        from ogscope.utils.environment import should_use_simulation_mode

        if not should_use_simulation_mode():
            from ogscope.web.camera_shared import get_camera_manager

            await get_camera_manager().stop()
    except Exception as e:
        logger.warning(f"关闭相机失败 / Failed to stop camera on shutdown: {e}")


# API 文档分组标签 / API documentation group tags
openapi_tags = [
    {
        "name": "Camera - 相机",
        "description": "相机控制与图像获取 / Camera control and image capture",
    },
    {
        "name": "Alignment - 极轴校准",
        "description": "极轴校准流程与状态 / Polar alignment workflow and status",
    },
    {
        "name": "System - 系统",
        "description": "系统信息与配置管理 / System information and configuration",
    },
    {
        "name": "Debug - 调试",
        "description": "调试控制台接口 / Debug console endpoints",
    },
    {
        "name": "Analysis - 分析",
        "description": "素材分析与任务管理 / Asset analysis and job management",
    },
    {
        "name": "Network - 网络",
        "description": "WiFi AP/STA 切换 / WiFi AP vs STA switching",
    },
    {
        "name": "Catalog - 星表",
        "description": "星表下载、索引与状态 / Catalog download, indexing, and status",
    },
]

# 创建 FastAPI 应用（禁用默认 ReDoc，使用自定义稳定版本）
# Create a FastAPI application (disable default ReDoc, use custom stable version)
app = FastAPI(
    title="OGScope API",
    description="电子极轴镜 Web API",
    version=__version__,
    lifespan=lifespan,
    openapi_tags=openapi_tags,
    redoc_url=None,
)

settings = get_settings()


def _spa_unavailable_html(title: str, detail: str) -> HTMLResponse:
    """Vite 产物缺失时的纯 HTML 提示（无 Jinja）/ Plain HTML when SPA build is missing (no Jinja)."""
    body = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"/><title>{title}</title></head>
<body style="font-family:system-ui,sans-serif;padding:1.5rem;max-width:42rem">
<h1 style="font-size:1.1rem">{title}</h1>
<p style="color:#444;line-height:1.5">{detail}</p>
<pre style="background:#f4f4f4;padding:0.75rem;overflow:auto">cd web/spa && npm ci && npm run build</pre>
</body></html>"""
    return HTMLResponse(content=body, status_code=503)


# 配置 CORS (允许跨域请求) / Configure CORS (allow cross-origin requests)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*"
    ],  # 生产环境应该限制具体域名 / Production environments should restrict specific domain names
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件 / Mount static files
if settings.static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static")

# 注册路由 / Register route
app.include_router(api_router, prefix="/api")


@app.get("/manifest.json")
async def web_manifest():
    """PWA 清单（原 web/manifest.json）/ PWA manifest at repo web/manifest.json."""
    path = settings.static_dir.parent / "manifest.json"
    if path.is_file():
        return FileResponse(path)
    return HTMLResponse("manifest not found", status_code=404)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """根路径：用户 HUD（Vite home 入口构建产物）/ Root: user HUD from Vite home entry."""
    _ = request
    home_index = settings.static_dir / "analysis-lab" / "home.html"
    if home_index.is_file():
        return FileResponse(home_index)
    return _spa_unavailable_html(
        "OGScope 前端未构建 / Frontend not built",
        "缺少 web/static/analysis-lab/home.html。请在 web/spa 执行 npm run build。",
    )


@app.get("/debug", response_class=HTMLResponse)
async def debug_console(request: Request):
    """统一调试后台入口 / Unified debug admin entry."""
    _ = request
    admin_index = settings.static_dir / "analysis-lab" / "system.html"
    if admin_index.is_file():
        return FileResponse(admin_index)
    return _spa_unavailable_html(
        "系统调试台未构建 / System debug SPA missing",
        "缺少 web/static/analysis-lab/system.html。",
    )


@app.get("/debug/system", response_class=HTMLResponse)
async def debug_system_console(request: Request):
    """兼容旧系统调试入口，重定向到新后台 / Legacy system debug entry."""
    _ = request
    return RedirectResponse(url="/debug", status_code=307)


@app.get("/debug/camera", response_class=HTMLResponse)
async def debug_camera_console(request: Request):
    """相机调试页（Vite camera 入口）/ Camera debug SPA."""
    _ = request
    camera_index = settings.static_dir / "analysis-lab" / "camera.html"
    if camera_index.is_file():
        return FileResponse(camera_index)
    return _spa_unavailable_html(
        "相机调试台未构建 / Camera debug SPA missing",
        "缺少 web/static/analysis-lab/camera.html。",
    )


@app.get("/debug/analysis", response_class=HTMLResponse)
async def debug_analysis_console(request: Request):
    """星空解算控制台（Vite analysis 入口）/ Plate solve lab SPA."""
    _ = request
    lab_index = settings.static_dir / "analysis-lab" / "index.html"
    if lab_index.is_file():
        return FileResponse(lab_index)
    return _spa_unavailable_html(
        "解算控制台未构建 / Analysis lab SPA missing",
        "缺少 web/static/analysis-lab/index.html。",
    )


@app.get("/api")
async def api_root():
    """API根路径 / API root path"""
    return {
        "name": "OGScope",
        "version": __version__,
        "status": "running",
        "docs": "/docs",
        "endpoints": {
            "camera": "/api/camera/",
            "alignment": "/api/alignment/",
            "system": "/api/system/",
            "network": "/api/network/",
            "analysis": "/api/analysis/",
        },
    }


@app.get("/redoc", include_in_schema=False)
async def custom_redoc():
    """自定义 ReDoc 页面，使用固定稳定版本 / Custom ReDoc page with pinned stable version"""
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - ReDoc",
        redoc_js_url="https://cdn.jsdelivr.net/npm/redoc@2.1.5/bundles/redoc.standalone.js",
    )


@app.get("/health")
async def health_check():
    """健康检查 / health check"""
    return {
        "status": "healthy",
        "version": __version__,
    }
