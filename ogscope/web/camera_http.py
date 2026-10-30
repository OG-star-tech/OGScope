"""相机预览的 HTTP 表示与客户端节流 / Camera preview HTTP representation and client throttling."""

import time

from fastapi import HTTPException
from fastapi.responses import Response
from starlette.requests import Request

from ogscope.config import get_settings
from ogscope.domain.camera.services import CameraDomainService, camera_domain_service

_PREVIEW_CLIENT_LAST_TS: dict[str, float] = {}


def _debug_preview_min_interval_sec() -> float:
    return max(0.0, float(get_settings().debug_preview_min_interval_ms)) / 1000.0


class CameraHttpService:
    """HTTP 适配依赖中性领域值，不反向引用 Web 实现 / HTTP adapts neutral domain values without reverse Web dependencies."""

    def __init__(self, domain: CameraDomainService = camera_domain_service) -> None:
        self.domain = domain

    async def get_preview(self, *, since_frame_id: int | None = None):
        """保留状态码和帧身份头 / Preserve HTTP status and frame identity headers."""
        code, frame = await self.domain.get_preview(since_frame_id=since_frame_id)
        if code == 304:
            return Response(status_code=304)
        if code != 200 or frame is None or frame.jpeg_frame is None:
            raise HTTPException(
                status_code=503,
                detail="暂无预览帧，请稍后重试 / No preview frame yet, retry shortly",
            )
        return Response(
            content=frame.jpeg_frame,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "X-Frame-Id": str(frame.frame_id),
                "X-Frame-Ts": str(frame.timestamp),
                "X-Frame-Width": str(frame.width),
                "X-Frame-Height": str(frame.height),
            },
        )

    async def get_rate_limited_preview(
        self, request: Request, *, since_frame_id: int | None = None
    ):
        if _debug_preview_min_interval_sec() > 0:
            client_host = request.client.host if request.client else "unknown"
            now = time.monotonic()
            last = _PREVIEW_CLIENT_LAST_TS.get(client_host, 0.0)
            if now - last < _debug_preview_min_interval_sec():
                return Response(status_code=304)
            _PREVIEW_CLIENT_LAST_TS[client_host] = now
        return await self.get_preview(since_frame_id=since_frame_id)


camera_http_service = CameraHttpService()
