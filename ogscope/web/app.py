"""
FastAPI Web 应用
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from loguru import logger

from ogscope.__version__ import __version__
from ogscope.config import get_settings
from ogscope.web.api.main import router as api_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """应用生命周期管理 / Application life cycle management"""
    # 启动时执行 / Execute at startup
    logger.info("初始化 Web 应用...")
    
    # TODO: 初始化数据库连接 / TODO: Initialize database connection
    # TODO: 初始化相机 / TODO: Initialize camera
    # TODO: 初始化其他资源 / TODO: Initialize other resources
    
    yield
    
    # 关闭时执行 / Execute on shutdown
    logger.info("清理资源...")
    # TODO: 关闭数据库连接 / TODO: Close database connection
    # TODO: 释放相机资源 / TODO: Release camera resources


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
]

# 创建 FastAPI 应用 / Create a FastAPI application
app = FastAPI(
    title="OGScope API",
    description="电子极轴镜 Web API",
    version=__version__,
    lifespan=lifespan,
    openapi_tags=openapi_tags,
)

# 初始化模板引擎 / Initialize template engine
settings = get_settings()
templates = Jinja2Templates(directory=str(settings.template_dir))

# 配置 CORS (允许跨域请求) / Configure CORS (allow cross-origin requests)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制具体域名 / Production environments should restrict specific domain names
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件 / Mount static files
if settings.static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static")

# 挂载Web模板和manifest / Mount web templates and manifests
if settings.template_dir.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/web", StaticFiles(directory=str(settings.template_dir.parent)), name="web")

# 注册路由 / Register route
app.include_router(api_router, prefix="/api")


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """根路径 - 返回主页面 / Root path - return to main page"""
    return templates.TemplateResponse(
        "index.html", 
        {
            "request": request,
            "version": __version__,
            "app_name": "OGScope"
        }
    )


@app.get("/debug", response_class=HTMLResponse)
async def debug_console(request: Request):
    """调试控制台页面 / Debug console page"""
    return templates.TemplateResponse(
        "debug.html", 
        {
            "request": request,
            "version": __version__,
            "app_name": "OGScope Debug Console"
        }
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
            "system": "/api/system/"
        }
    }


@app.get("/health")
async def health_check():
    """健康检查 / health check"""
    return {
        "status": "healthy",
        "version": __version__,
    }

