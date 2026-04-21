"""
硬件平面客户端 / Hardware plane client.
"""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

from ogscope.platform.hardware_plane.contracts import (
    PlaneErrorCode,
    PlaneMethod,
    error_payload,
)
from ogscope.platform.hardware_plane.daemon import HardwarePlaneDaemon


class RemotePlaneTransport(Protocol):
    """远端硬件平面传输协议 / Remote hardware-plane transport protocol."""

    async def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout_ms: int = 800,
    ) -> dict[str, Any]:
        """执行远端调用 / Perform remote call."""


class HardwarePlaneClient:
    """面向应用层的硬件平面客户端 / App-facing hardware plane client."""

    def __init__(
        self,
        daemon: HardwarePlaneDaemon,
        *,
        default_timeout_ms: int = 800,
        remote_sensor_transport: RemotePlaneTransport | None = None,
        remote_sensor_enabled: bool = False,
        runtime_profile: dict[str, Any] | None = None,
    ) -> None:
        self._daemon = daemon
        self._default_timeout_ms = max(50, int(default_timeout_ms))
        self._remote_sensor_transport = remote_sensor_transport
        self._remote_sensor_enabled = bool(remote_sensor_enabled and remote_sensor_transport)
        self._runtime_profile = dict(runtime_profile or {})

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
        if self._remote_sensor_enabled and self._remote_sensor_transport is not None:
            budget = max(50, int(self._default_timeout_ms))
            try:
                return await asyncio.wait_for(
                    self._remote_sensor_transport.call(
                        PlaneMethod.SENSOR_READ.value,
                        {"name": name},
                        timeout_ms=budget,
                    ),
                    timeout=budget / 1000.0,
                )
            except asyncio.TimeoutError:
                return error_payload(
                    code=PlaneErrorCode.TIMEOUT,
                    message="delegated sensor call timeout",
                )
            except Exception as exc:  # pragma: no cover - 防御性兜底 / defensive guard
                return error_payload(
                    code=PlaneErrorCode.UNAVAILABLE,
                    message=f"delegated sensor call failed: {exc}",
                )
        return await self._call(PlaneMethod.SENSOR_READ, {"name": name})

    async def device_command(
        self,
        target: str,
        action: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        return await self._call(
            PlaneMethod.DEVICE_COMMAND,
            {"target": target, "action": action, "payload": payload or {}},
            timeout_ms=timeout_ms,
        )

    async def event_subscribe(self, topic: str) -> dict[str, Any]:
        return await self._call(PlaneMethod.EVENT_SUBSCRIBE, {"topic": topic})

    def runtime_profile(self) -> dict[str, Any]:
        """运行时角色信息 / Runtime role profile."""
        return dict(self._runtime_profile)

