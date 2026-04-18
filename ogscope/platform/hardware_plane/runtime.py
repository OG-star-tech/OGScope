"""
硬件平面运行时单例 / Runtime singleton for hardware plane.
"""

from __future__ import annotations

from ogscope.config import Settings, get_settings
from ogscope.platform.hardware_plane.client import HardwarePlaneClient
from ogscope.platform.hardware_plane.daemon import HardwarePlaneDaemon

_daemon: HardwarePlaneDaemon | None = None
_client: HardwarePlaneClient | None = None


def get_hardware_plane_daemon() -> HardwarePlaneDaemon:
    """获取守护进程单例 / Get daemon singleton."""
    global _daemon
    if _daemon is None:
        _daemon = HardwarePlaneDaemon()
    return _daemon


def get_hardware_plane_client() -> HardwarePlaneClient:
    """获取客户端单例 / Get client singleton."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = HardwarePlaneClient(
            get_hardware_plane_daemon(),
            default_timeout_ms=settings.hardware_plane_rpc_timeout_ms,
        )
    return _client


async def start_hardware_plane(settings: Settings | None = None) -> None:
    """启动硬件平面 / Start hardware plane."""
    cfg = settings or get_settings()
    if not cfg.hardware_plane_enabled:
        return
    daemon = get_hardware_plane_daemon()
    await daemon.start()


async def stop_hardware_plane() -> None:
    """停止硬件平面 / Stop hardware plane."""
    daemon = get_hardware_plane_daemon()
    await daemon.stop()

