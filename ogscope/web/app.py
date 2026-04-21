"""
FastAPI Web 应用
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from copy import deepcopy
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from ogscope.__version__ import __version__
from ogscope.config import get_settings
from ogscope.platform.hardware_plane.runtime import (
    describe_hardware_plane_profile,
    get_hardware_plane_client,
    get_hardware_plane_daemon,
    start_hardware_plane,
    stop_hardware_plane,
)
from ogscope.web.api.main import router as api_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """应用生命周期管理 / Application life cycle management"""
    # 启动时执行 / Execute at startup
    logger.info("初始化 Web 应用...")
    settings = get_settings()
    hp_profile = describe_hardware_plane_profile(settings)
    logger.info(
        "硬件角色={} 传感器来源={} 本地传感器={} HMI={} UI={} 远端UDS={}",
        hp_profile["role"],
        hp_profile["sensor_source"],
        hp_profile["enable_local_sensors"],
        hp_profile["enable_hmi"],
        hp_profile["enable_ui"],
        hp_profile["remote_uds_socket"],
    )
    phase_p0_started = asyncio.get_running_loop().time()

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

    await start_hardware_plane(settings)
    daemon = get_hardware_plane_daemon()
    daemon.begin_phase("P0", "api gateway ready")
    asyncio.create_task(_warm_camera())
    # 解算器预热改为启动阶段阻塞完成，避免首个解算请求与后台预热竞态导致“第一次明显变慢”
    # Warm the solver synchronously during startup to avoid first-request cold-start race.
    await _warm_solver()
    daemon.begin_phase("P2", "sensor and hmi services ready")
    if settings.hardware_plane_camera_autostart:
        try:
            await daemon.handle_call(
                "device.command",
                {"target": "camera", "action": "start", "payload": {}},
            )
            daemon.begin_phase("P3", "camera service auto-started")
        except Exception as e:
            logger.warning(
                "相机自动启动失败，将按需延迟启动 / Camera auto-start failed, fallback to lazy start: {}",
                e,
            )
    phase_elapsed_ms = int((asyncio.get_running_loop().time() - phase_p0_started) * 1000)
    logger.info("启动阶段完成 / Startup phases ready in {} ms", phase_elapsed_ms)

    try:
        from ogscope.platform.hardware.wifi_emergency_gpio import (
            wifi_emergency_gpio_monitor,
        )

        wifi_emergency_gpio_monitor.start()
    except Exception as e:
        logger.warning("应急 GPIO 启动失败 / Emergency GPIO start failed: {}", e)

    yield

    # 关闭时执行 / Execute on shutdown
    logger.info("清理资源...")
    try:
        from ogscope.platform.hardware.wifi_emergency_gpio import (
            wifi_emergency_gpio_monitor,
        )

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
    await stop_hardware_plane()


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
        "name": "Dev - 系统状态",
        "description": "开发者系统状态接口（内部使用）/ Developer system status endpoints (internal)",
    },
    {
        "name": "Dev - 调试工具",
        "description": "开发者调试接口（内部使用）/ Developer debugging endpoints (internal)",
    },
    {
        "name": "Dev - 分析实验",
        "description": "开发者分析实验接口（内部使用）/ Developer analysis lab endpoints (internal)",
    },
    {
        "name": "Network - 网络",
        "description": "WiFi AP/STA 切换 / WiFi AP vs STA switching",
    },
    {
        "name": "Core - 标准契约",
        "description": "对外稳定 REST 契约 / Stable REST contract for external callers",
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
    docs_url=None,
    redoc_url=None,
)

settings = get_settings()
hardware_profile = describe_hardware_plane_profile(settings)


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
if bool(hardware_profile["enable_ui"]) and settings.static_dir.exists():
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
    if not bool(hardware_profile["enable_ui"]):
        return HTMLResponse("UI disabled in subordinate mode", status_code=404)
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
    if not bool(hardware_profile["enable_ui"]):
        return HTMLResponse("UI disabled in subordinate mode", status_code=404)
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
    if not bool(hardware_profile["enable_ui"]):
        return HTMLResponse("UI disabled in subordinate mode", status_code=404)
    return RedirectResponse(url="/debug", status_code=307)


@app.get("/debug/camera", response_class=HTMLResponse)
async def debug_camera_console(request: Request):
    """相机调试页（Vite camera 入口）/ Camera debug SPA."""
    _ = request
    if not bool(hardware_profile["enable_ui"]):
        return HTMLResponse("UI disabled in subordinate mode", status_code=404)
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
    if not bool(hardware_profile["enable_ui"]):
        return HTMLResponse("UI disabled in subordinate mode", status_code=404)
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
        "role": hardware_profile["role"],
        "sensor_source": hardware_profile["sensor_source"],
        "docs": "/docs",
        "docs_dev": "/docs/dev",
        "endpoints": {
            "camera": "/api/camera/",
            "alignment": "/api/alignment/",
            "system": "/api/dev/system/",
            "hardware_plane": "/api/dev/system/hardware-plane/status",
            "system_legacy": "/api/system/",
            "network": "/api/network/",
            "analysis": "/api/dev/analysis/",
            "debug": "/api/dev/debug/",
            "core": "/api/core/v1/",
        },
    }


def _iter_component_refs(node: Any) -> set[str]:
    """递归提取本地 components 引用 / Recursively extract local component refs."""
    refs: set[str] = set()
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/"):
            refs.add(ref)
        for value in node.values():
            refs.update(_iter_component_refs(value))
    elif isinstance(node, list):
        for item in node:
            refs.update(_iter_component_refs(item))
    return refs


def _prune_openapi_components(raw: dict, filtered_paths: dict[str, dict]) -> None:
    """按路径实际引用裁剪 components / Prune components by actual refs in filtered paths."""
    components = raw.get("components")
    if not isinstance(components, dict):
        return
    used: dict[str, set[str]] = {}
    pending_refs = list(_iter_component_refs(filtered_paths))
    while pending_refs:
        ref = pending_refs.pop()
        parts = ref.split("/")
        if len(parts) != 4:
            continue
        _, _, section, name = parts
        if section not in components or not isinstance(components.get(section), dict):
            continue
        section_used = used.setdefault(section, set())
        if name in section_used:
            continue
        section_used.add(name)
        target = components[section].get(name)
        pending_refs.extend(_iter_component_refs(target))

    pruned_components: dict[str, dict] = {}
    for section, values in components.items():
        if not isinstance(values, dict):
            continue
        keep_names = used.get(section, set())
        if not keep_names:
            continue
        kept = {name: data for name, data in values.items() if name in keep_names}
        if kept:
            pruned_components[section] = kept
    raw["components"] = pruned_components


def _filtered_openapi_schema(*, mode: str) -> dict:
    """按路径过滤 OpenAPI schema / Build filtered OpenAPI schema by path domain."""
    raw = deepcopy(app.openapi())
    paths = raw.get("paths", {})
    filtered_paths: dict[str, dict] = {}
    if mode == "core":
        filtered_paths = {
            path: data for path, data in paths.items() if path.startswith("/api/core/v1/")
        }
    elif mode == "dev":
        filtered_paths = {
            path: data for path, data in paths.items() if path.startswith("/api/dev/")
        }
    else:
        filtered_paths = paths
    raw["paths"] = filtered_paths
    if mode in {"core", "dev"}:
        _prune_openapi_components(raw, filtered_paths)
    used_tags: set[str] = set()
    for item in filtered_paths.values():
        for op in item.values():
            if isinstance(op, dict):
                for tag in op.get("tags", []):
                    used_tags.add(str(tag))
    tags = raw.get("tags", [])
    raw["tags"] = [tag for tag in tags if tag.get("name") in used_tags]
    return raw


@app.get("/openapi-core.json", include_in_schema=False)
async def openapi_core_json() -> JSONResponse:
    """标准契约 OpenAPI / Core-only OpenAPI."""
    return JSONResponse(_filtered_openapi_schema(mode="core"))


@app.get("/openapi-dev.json", include_in_schema=False)
async def openapi_dev_json() -> JSONResponse:
    """开发者 OpenAPI / Dev-only OpenAPI."""
    return JSONResponse(_filtered_openapi_schema(mode="dev"))


@app.get("/openapi-all.json", include_in_schema=False)
async def openapi_all_json() -> JSONResponse:
    """全量 OpenAPI / Full OpenAPI."""
    return JSONResponse(_filtered_openapi_schema(mode="all"))


@app.get("/docs", include_in_schema=False)
async def docs_core() -> HTMLResponse:
    """默认文档：标准契约 / Default docs: core contract."""
    return get_swagger_ui_html(
        openapi_url="/openapi-core.json",
        title=f"{app.title} - Core API Docs",
    )


@app.get("/docs/dev", include_in_schema=False)
async def docs_dev() -> HTMLResponse:
    """开发者文档 / Developer docs."""
    return get_swagger_ui_html(
        openapi_url="/openapi-dev.json",
        title=f"{app.title} - Dev API Docs",
    )


@app.get("/docs/all", include_in_schema=False)
async def docs_all() -> HTMLResponse:
    """全量文档 / Full docs."""
    return get_swagger_ui_html(
        openapi_url="/openapi-all.json",
        title=f"{app.title} - Full API Docs",
    )


@app.get("/redoc", include_in_schema=False)
async def custom_redoc():
    """自定义 ReDoc 页面，使用固定稳定版本 / Custom ReDoc page with pinned stable version"""
    return get_redoc_html(
        openapi_url="/openapi-core.json",
        title=f"{app.title} - ReDoc",
        redoc_js_url="https://cdn.jsdelivr.net/npm/redoc@2.1.5/bundles/redoc.standalone.js",
    )


@app.get("/health")
async def health_check():
    """健康检查 / health check"""
    hardware_started = False
    metrics: dict[str, Any] = {}
    profile: dict[str, Any] = {}
    try:
        client = get_hardware_plane_client()
        payload = await client.status_get()
        data = payload.get("data", {}) if payload.get("success") else {}
        hardware_started = bool(data.get("started", False))
        metrics = data.get("metrics", {}) or {}
        profile = data.get("profile", {}) or client.runtime_profile()
    except Exception:
        hardware_started = False
    return {
        "status": "healthy",
        "version": __version__,
        "hardware_plane": {
            "started": hardware_started,
            "metrics": metrics,
            "profile": profile,
        },
    }
