"""
相机硬件服务 / Camera hardware service.
"""

from __future__ import annotations

from typing import Any

from ogscope.platform.hardware_plane.data_plane import FrameRingBuffer


class CameraPlaneService:
    """相机控制 + 数据面桥接 / Camera control with data-plane bridge."""

    name = "camera-service"

    def __init__(self, *, ring_capacity: int = 8) -> None:
        self._running = False
        self._ring = FrameRingBuffer(capacity=ring_capacity)
        self._last_frame_id = 0

    async def start(self) -> None:
        from ogscope.web.camera_shared import get_camera_manager

        await get_camera_manager().ensure_started()
        self._running = True

    async def stop(self) -> None:
        from ogscope.web.camera_shared import get_camera_manager

        await get_camera_manager().stop()
        self._running = False

    async def status(self) -> dict[str, Any]:
        from ogscope.web.camera_shared import get_camera_manager

        camera_status = await get_camera_manager().status()
        return {
            "running": self._running,
            "connected": bool(camera_status.get("connected", False)),
            "streaming": bool(camera_status.get("streaming", False)),
            "recording": bool(camera_status.get("recording", False)),
            "last_frame_id": self._last_frame_id,
        }

    async def publish_latest_preview(self) -> dict[str, Any]:
        from ogscope.web.camera_shared import get_camera_manager

        manager = get_camera_manager()
        await manager.ensure_started()
        snap = await manager.get_cached_frame_snapshot()
        if snap is None or snap.jpeg_frame is None:
            return {"published": False, "reason": "no_frame"}
        packet = self._ring.publish(snap.jpeg_frame, media_type="image/jpeg")
        self._last_frame_id = packet.frame_id
        return {
            "published": True,
            "frame_id": packet.frame_id,
            "timestamp": packet.timestamp,
        }

    async def latest_frame(self) -> dict[str, Any]:
        packet = self._ring.latest()
        if packet is None:
            return {"available": False}
        return {
            "available": True,
            "frame_id": packet.frame_id,
            "timestamp": packet.timestamp,
            "media_type": packet.media_type,
            "payload": packet.payload,
        }

    async def command(
        self, action: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        _ = payload
        if action == "start":
            await self.start()
            return {"accepted": True}
        if action == "stop":
            await self.stop()
            return {"accepted": True}
        if action == "publish_latest_preview":
            return await self.publish_latest_preview()
        if action == "latest_frame":
            frame = await self.latest_frame()
            frame.pop("payload", None)
            return frame
        return {"accepted": False, "message": f"unsupported action: {action}"}
