"""
OGScope 主程序入口
"""
import asyncio
import sys
from pathlib import Path
from typing import Optional

import uvicorn
from loguru import logger

from ogscope.__version__ import __version__
from ogscope.config import Settings, get_settings
from ogscope.utils.logging_config import setup_logging


def setup_environment() -> Settings:
    """初始化环境"""
    # 加载配置
    settings = get_settings()
    
    # 配置日志
    setup_logging(settings.log_level, settings.log_file)
    
    logger.info(f"OGScope v{__version__} 启动中...")
    logger.info(f"运行环境: {settings.environment}")
    logger.info(f"日志级别: {settings.log_level}")
    
    return settings


async def main() -> int:
    """主函数"""
    try:
        settings = setup_environment()
        
        # TODO: 初始化各个模块
        # - 相机模块
        # - 显示模块
        # - 算法模块
        
        # 启动 FastAPI Web 服务
        logger.info(f"启动 Web 服务: http://{settings.host}:{settings.port}")
        
        config = uvicorn.Config(
            "ogscope.web.app:app",
            host=settings.host,
            port=settings.port,
            reload=settings.reload,
            log_level=settings.log_level.lower(),
        )
        server = uvicorn.Server(config)
        await server.serve()
        
        return 0
        
    except KeyboardInterrupt:
        logger.info("收到退出信号 (Ctrl+C)")
        return 0
    except Exception as e:
        logger.exception(f"发生错误: {e}")
        return 1
    finally:
        logger.info("OGScope 已关闭")


def cli() -> None:
    """命令行入口点"""
    exit_code = asyncio.run(main())
    sys.exit(exit_code)


if __name__ == "__main__":
    cli()

