"""
硬件平面客户端 / Hardware plane client.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ogscope.hardware_plane.contracts import PlaneMethod
from ogscope.hardware_plane.daemon import HardwarePlaneDaemon


class HardwarePlaneClient:
    """面向应用层的硬件平面客户端 / App-facing hardware plane client."""

    def __init__(
        self,
        daemon: HardwarePlaneDaemon,
        *,
        default_timeout_ms: int = 800,
    ) -> None:
        self._daemon = daemon
        self._default_timeout_ms = max(50, int(default_timeout_ms))

    async def _call(
        self,
        method: PlaneMethod,
        params: dict[str, Any] | None = None,
        timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        budget = max(50, int(timeout_ms or self._default_timeout_ms))
        return await asyncio.wait_for(
            self._daemon.handle_call(method.value, params),
            timeout=budget / 1000.0,
        )

    async def status_get(self) -> dict[str, Any]:
        return await self._call(PlaneMethod.STATUS_GET)

    async def capability_list(self) -> dict[str, Any]:
        return await self._call(PlaneMethod.CAPABILITY_LIST)

    async def sensor_read(self, name: str) -> dict[str, Any]:
        return await self._call(PlaneMethod.SENSOR_READ, {"name": name})

    async def device_command(
        self,
        target: str,
        action: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._call(
            PlaneMethod.DEVICE_COMMAND,
            {"target": target, "action": action, "payload": payload or {}},
        )

    async def event_subscribe(self, topic: str) -> dict[str, Any]:
        return await self._call(PlaneMethod.EVENT_SUBSCRIBE, {"topic": topic})

