"""
MJPEG 长连接并发限制 / Concurrent MJPEG stream limiter
"""

from ogscope.domain.camera.stream_limiter import (
    MjpegStreamLimiter,
    get_mjpeg_stream_limiter,
)

__all__ = ["MjpegStreamLimiter", "get_mjpeg_stream_limiter"]
