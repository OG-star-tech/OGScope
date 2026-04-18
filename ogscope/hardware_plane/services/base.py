"""
硬件服务基础协议 / Base protocol for hardware services.
"""

from __future__ import annotations

from typing import Any, Protocol


class HardwareService(Protocol):
    """硬件服务协议 / Hardware service protocol."""

    name: str

    async def start(self) -> None:
        """启动服务 / Start service."""

    async def stop(self) -> None:
        """停止服务 / Stop service."""

    async def status(self) -> dict[str, Any]:
        """读取服务状态 / Read service status."""

    async def command(self, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """执行命令 / Execute command."""

