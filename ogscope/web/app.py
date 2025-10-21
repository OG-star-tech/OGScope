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
    """应用生命周期管理"""
    # 启动时执行
    logger.info("初始化 Web 应用...")
    
    # TODO: 初始化数据库连接
    # TODO: 初始化相机
    # TODO: 初始化其他资源
    
    yield
    
    # 关闭时执行
    logger.info("清理资源...")
    # TODO: 关闭数据库连接
    # TODO: 释放相机资源


# 创建 FastAPI 应用
app = FastAPI(
    title="OGScope API",
    description="电子极轴镜 Web API",
    version=__version__,
    lifespan=lifespan,
)

# 初始化模板引擎
settings = get_settings()
templates = Jinja2Templates(directory=str(settings.template_dir))

# 配置 CORS (允许跨域请求)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件
if settings.static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static")

# 挂载Web模板和manifest
if settings.template_dir.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/web", StaticFiles(directory=str(settings.template_dir.parent)), name="web")

# 注册路由
app.include_router(api_router, prefix="/api")


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """根路径 - 返回主页面"""
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
    """调试控制台页面"""
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
    """API根路径"""
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
    """健康检查"""
    return {
        "status": "healthy",
        "version": __version__,
    }

