"""
日志配置模块
"""
import sys
from pathlib import Path
from typing import Optional

from loguru import logger


def setup_logging(
    level: str = "INFO",
    log_file: Optional[Path] = None,
) -> None:
    """
    配置 Loguru 日志系统
    
    Args:
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: 日志文件路径，None 表示不输出到文件
    """
    # 移除默认的 handler
    logger.remove()
    
    # 添加控制台输出 handler
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
               "<level>{message}</level>",
        level=level,
        colorize=True,
    )
    
    # 添加文件输出 handler（如果指定）
    if log_file:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        logger.add(
            log_file,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
                   "{name}:{function}:{line} | {message}",
            level=level,
            rotation="10 MB",  # 日志文件大小达到 10MB 时轮转
            retention="30 days",  # 保留 30 天的日志
            compression="zip",  # 压缩旧日志
            enqueue=True,  # 异步写入
        )
        
        logger.info(f"日志文件: {log_file.absolute()}")

