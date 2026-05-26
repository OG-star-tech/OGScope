"""
相机 MJPEG 流共享实现 / Shared camera MJPEG streaming implementation.
"""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from starlette.requests import Request

from ogscope.config import get_settings
from ogscope.domain.camera.services import camera_domain_service
from ogscope.domain.camera.stream_limiter import get_mjpeg_stream_limiter
from ogscope.web.mjpeg_stream_helpers import mjpeg_sleep_or_disconnect


async def build_camera_mjpeg_stream(
    request: Request,
    *,
    image_format: str,
    quality: int,
    limit_detail: str,
    timeout_log_message: str,
    logger: logging.Logger,
) -> StreamingResponse:
    """构建 MJPEG 流响应 / Build MJPEG stream response."""
    limiter = get_mjpeg_stream_limiter()
    if not await limiter.try_acquire():
        _path = str(getattr(getattr(request, "url", None), "path", "") or "")
        logger.warning(
            "mjpeg_try_acquire_rejected active=%s max=%s path=%s",
            limiter.active_clients,
            limiter.max_clients,
            _path,
        )
        raise HTTPException(status_code=503, detail=limit_detail)
    boundary = "frame"
    settings = get_settings()
    min_emit_interval = 1.0 / max(1, int(settings.shared_preview_fps))
    fetch_timeout_s = settings.stream_mjpeg_frame_fetch_timeout_ms / 1000.0
    content_type = "image/jpeg" if image_format.lower() == "jpeg" else "image/png"

    async def frame_generator():
        try:
            last_snap_frame_id = -1
            last_emit_mono = 0.0
            while True:
                if await request.is_disconnected():
                    break
                try:
                    code, data, snap_id = await asyncio.wait_for(
                        camera_domain_service.get_stream_frame_bytes(
                            image_format, quality, since_frame_id=last_snap_frame_id
                        ),
                        timeout=fetch_timeout_s,
                    )
                except asyncio.TimeoutError:
                    logger.warning(timeout_log_message)
                    break
                if code == 304:
                    if not await mjpeg_sleep_or_disconnect(request, 0.03):
                        break
                    continue
                if code != 200 or data is None:
                    if not await mjpeg_sleep_or_disconnect(request, 0.05):
                        break
                    continue
                now = time.monotonic()
                wait = last_emit_mono + min_emit_interval - now
                if wait > 0 and not await mjpeg_sleep_or_disconnect(request, wait):
                    break
                last_snap_frame_id = snap_id
                last_emit_mono = time.monotonic()
                yield (
                    b"--"
                    + boundary.encode()
                    + b"\r\n"
                    + b"Content-Type: "
                    + content_type.encode()
                    + b"\r\n"
                    + b"Content-Length: "
                    + str(len(data)).encode()
                    + b"\r\n\r\n"
                    + data
                    + b"\r\n"
                )
        finally:
            await limiter.release()

    return StreamingResponse(
        frame_generator(),
        media_type=f"multipart/x-mixed-replace; boundary={boundary}",
    )
