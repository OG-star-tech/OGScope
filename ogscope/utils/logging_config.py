"""
日志配置模块
"""

import logging
import sys
from pathlib import Path
from typing import Optional

from loguru import logger


def setup_logging(
    level: str = "INFO",
    log_file: Optional[Path] = None,
    *,
    development_mode: bool = False,
) -> None:
    """
    配置 Loguru 日志系统

    Args:
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: 日志文件路径，None 表示不输出到文件
        development_mode: 开发模式：同步提升标准库 logging（第三方库常用）/ Dev mode: bump stdlib logging too
    """
    # 移除默认的 handler / Remove default handler
    logger.remove()

    # 添加控制台输出 handler / Add console output handler
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>",
        level=level,
        colorize=True,
    )

    # 添加文件输出 handler（如果指定） / Add file output handler (if specified)
    if log_file:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        logger.add(
            log_file,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
            "{name}:{function}:{line} | {message}",
            level=level,
            rotation="10 MB",  # 日志文件大小达到 10MB 时轮转 / Rotate log files when size reaches 10MB
            retention="30 days",  # 保留 30 天的日志 / Keep logs for 30 days
            compression="zip",  # 压缩旧日志 / Compress old logs
            enqueue=True,  # 异步写入 / Asynchronous writing
        )

        logger.info(f"日志文件: {log_file.absolute()}")

    # 第三方库（libcamera/picamera2/tetra3 等）通常走标准库 logging；开发模式下同步提升根 logger
    # Third-party stacks (libcamera/picamera2/tetra3, …) often use stdlib logging; align root logger in dev mode.
    if development_mode:
        lvl = str(level).upper()
        py_level = getattr(logging, lvl, logging.INFO)
        # Python 3.8+：force 重新初始化，避免重复启动时 handler 叠加 / force re-init to avoid duplicate handlers
        try:
            logging.basicConfig(
                level=py_level,
                format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                force=True,
            )
        except TypeError:
            logging.basicConfig(
                level=py_level,
                format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            )
        logging.captureWarnings(True)
        # Tetra3 使用 logging.getLogger('tetra3.Tetra3')；显式对齐，避免仍停留在 INFO / Align Tetra3 logger explicitly
        logging.getLogger("tetra3").setLevel(py_level)
        logging.getLogger("tetra3.Tetra3").setLevel(py_level)
