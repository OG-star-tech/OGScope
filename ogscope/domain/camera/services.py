"""
相机域服务 / Camera domain services.
"""

from __future__ import annotations

import io
import logging
import os
import time
from typing import Any

from fastapi import HTTPException
from fastapi.responses import Response, StreamingResponse
from starlette.requests import Request

from ogscope.config import get_settings
from ogscope.web.api.debug.services import DebugCameraService, DebugFileService, DebugPresetService
from ogscope.domain.camera.stream_limiter import get_mjpeg_stream_limiter

logger = logging.getLogger(__name__)

_PREVIEW_CLIENT_LAST_TS: dict[str, float] = {}
_DEBUG_PREVIEW_MIN_INTERVAL_SEC = max(
    0.0,
    float(os.getenv("OGSCOPE_DEBUG_PREVIEW_MIN_INTERVAL_MS", "150") or "150") / 1000.0,
)


class CameraDomainService:
    """中性相机域能力门面 / Neutral camera domain facade."""

    async def get_status(self) -> dict[str, Any]:
        return await DebugCameraService.get_camera_status()

    async def start(self) -> dict[str, Any]:
        return await DebugCameraService.start_camera()

    async def stop(self) -> dict[str, Any]:
        return await DebugCameraService.stop_camera()

    async def set_auto_exposure_mode(self, enabled: bool):
        return await DebugCameraService.set_auto_exposure_mode(enabled)

    async def update_settings(self, settings: dict[str, Any]):
        return await DebugCameraService.update_settings(settings)

    async def set_fps(self, fps: int):
        return await DebugCameraService.set_fps(fps)

    async def set_size(self, width: int, height: int):
        return await DebugCameraService.set_size(width, height)

    async def set_rotation(self, rotation: int):
        return await DebugCameraService.set_rotation(rotation)

    async def set_mirror(self, flip_horizontal: bool, flip_vertical: bool):
        return await DebugCameraService.set_mirror(flip_horizontal, flip_vertical)

    async def set_sampling_mode(self, mode: str):
        return await DebugCameraService.set_sampling_mode(mode)

    async def set_color_mode(self, mode: str):
        return await DebugCameraService.set_color_mode(mode)

    async def set_white_balance(self, mode: str, gain_r: float, gain_b: float):
        return await DebugCameraService.set_white_balance(mode, gain_r, gain_b)

    async def get_stream_frame_bytes(
        self, image_format: str, quality: int, *, since_frame_id: int
    ):
        return await DebugCameraService.get_stream_frame_bytes(
            image_format, quality, since_frame_id=since_frame_id
        )

    async def get_preview(self, *, since_frame_id: int | None = None):
        return await DebugCameraService.get_preview(since_frame_id=since_frame_id)

    async def get_rate_limited_preview(
        self, request: Request, *, since_frame_id: int | None = None
    ):
        if _DEBUG_PREVIEW_MIN_INTERVAL_SEC > 0:
            client_host = request.client.host if request.client else "unknown"
            now = time.monotonic()
            last = _PREVIEW_CLIENT_LAST_TS.get(client_host, 0.0)
            if now - last < _DEBUG_PREVIEW_MIN_INTERVAL_SEC:
                return Response(status_code=304)
            _PREVIEW_CLIENT_LAST_TS[client_host] = now
        return await self.get_preview(since_frame_id=since_frame_id)

    async def get_product_camera_status(
        self,
        *,
        simulation_mode: bool,
        is_streaming: bool,
        simulation_config: dict[str, Any],
    ) -> dict[str, Any]:
        if simulation_mode:
            return {
                "connected": True,
                "streaming": is_streaming,
                "resolution": [1920, 1080],
                "fps": 30,
                "mode": "simulation",
                "simulation_config": simulation_config,
            }
        try:
            from ogscope.web.camera_shared import get_camera_manager

            status = await get_camera_manager().status()
            info = status.get("info", {}) if isinstance(status, dict) else {}
            width = int(info.get("output_width") or info.get("width") or 1920)
            height = int(info.get("output_height") or info.get("height") or 1080)
            fps = int(info.get("fps") or 30)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"读取相机状态失败: {exc}")
            status = {"connected": False, "streaming": False}
            width, height, fps = 1920, 1080, 30
        return {
            "connected": bool(status.get("connected")),
            "streaming": bool(status.get("streaming")),
            "resolution": [int(width), int(height)],
            "fps": int(fps),
            "mode": "real",
            "runtime_overrides": status.get("runtime_overrides", {}),
        }

    async def get_product_camera_preview(
        self,
        *,
        simulation_mode: bool,
        is_streaming: bool,
        virtual_stream: Any,
        since_frame_id: int | None = None,
    ):
        if simulation_mode:
            if not is_streaming:
                placeholder_image = io.BytesIO()
                placeholder_image.write(
                    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x01\x90\x00\x00\x00\xf0\x08\x02\x00\x00\x00"
                )
                placeholder_image.seek(0)
                return StreamingResponse(
                    placeholder_image,
                    media_type="image/png",
                    headers={"Cache-Control": "no-cache"},
                )
            try:
                frame_data = virtual_stream.generate_frame()
                return StreamingResponse(
                    io.BytesIO(frame_data),
                    media_type="image/jpeg",
                    headers={"Cache-Control": "no-cache"},
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(f"生成虚拟视频帧失败: {exc}")
                raise HTTPException(status_code=500, detail="生成视频帧失败") from exc
        try:
            return await self.get_preview(since_frame_id=since_frame_id)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error(f"获取真实相机预览失败: {exc}")
            raise HTTPException(status_code=500, detail="获取预览失败") from exc


class FileDomainService:
    """文件域门面 / File domain facade."""

    async def list_files(self) -> dict[str, Any]:
        return await DebugFileService.get_files()

    async def get_file_info(self, filename: str) -> dict[str, Any]:
        return await DebugFileService.get_file_info(filename)


class StreamStateDomainService:
    """流状态门面 / Stream state facade."""

    def get_stream_status(self) -> dict[str, int]:
        limiter = get_mjpeg_stream_limiter()
        settings = get_settings()
        return {
            "max_clients": int(limiter.max_clients),
            "active_clients": int(limiter.active_clients),
            "frame_fetch_timeout_ms": int(settings.stream_mjpeg_frame_fetch_timeout_ms),
            "target_preview_fps": int(os.getenv("OGSCOPE_SHARED_PREVIEW_FPS", "8") or "8"),
        }


camera_domain_service = CameraDomainService()
file_domain_service = FileDomainService()
stream_state_domain_service = StreamStateDomainService()

__all__ = [
    "DebugCameraService",
    "DebugFileService",
    "DebugPresetService",
    "CameraDomainService",
    "FileDomainService",
    "camera_domain_service",
    "file_domain_service",
    "stream_state_domain_service",
]

