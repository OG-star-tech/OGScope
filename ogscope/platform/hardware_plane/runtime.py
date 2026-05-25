"""
硬件平面运行时单例 / Runtime singleton for hardware plane.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from ogscope.config import Settings, get_settings
from ogscope.platform.hardware_plane.client import HardwarePlaneClient
from ogscope.platform.hardware_plane.daemon import HardwarePlaneDaemon
from ogscope.platform.hardware_plane.transport.jsonrpc_uds import JsonRpcUdsClient

_daemon: HardwarePlaneDaemon | None = None
_client: HardwarePlaneClient | None = None
_runtime_signature: tuple[Any, ...] | None = None


def _profile_from_settings(settings: Settings) -> dict[str, Any]:
    role = str(settings.hardware_plane_role or "standalone").strip().lower()
    if role not in {"standalone", "subordinate"}:
        logger.warning("未知硬件平面角色，回退 standalone / Unknown role: {}", role)
        role = "standalone"
    subordinate = role == "subordinate"
    enable_local_sensors = bool(settings.enable_local_sensors) and not subordinate
    enable_hmi = bool(settings.enable_hmi) and not subordinate
    # 在 subordinate 模式保留调试台可见性，冲突能力由 API 裁剪控制
    # Keep debug UI available in subordinate mode; conflict features are gated by API routing.
    enable_ui = bool(settings.enable_ui)
    sensor_source = "remote_delegated" if subordinate else "local"
    return {
        "role": role,
        "subordinate_mode": subordinate,
        "enable_local_sensors": enable_local_sensors,
        "enable_hmi": enable_hmi,
        "enable_ui": enable_ui,
        "sensor_source": sensor_source,
        "camera_source": "local_ogscope",
        "remote_uds_socket": str(settings.hardware_plane_remote_uds_socket),
    }


def describe_hardware_plane_profile(settings: Settings | None = None) -> dict[str, Any]:
    """对外暴露硬件平面角色视图 / Public hardware-plane profile snapshot."""
    return _profile_from_settings(settings or get_settings())


def _signature_from_settings(settings: Settings) -> tuple[Any, ...]:
    profile = _profile_from_settings(settings)
    return (
        profile["role"],
        profile["enable_local_sensors"],
        profile["enable_hmi"],
        profile["enable_ui"],
        profile["sensor_source"],
        profile["remote_uds_socket"],
        settings.hardware_plane_rpc_timeout_ms,
    )


def _ensure_runtime(settings: Settings) -> None:
    global _daemon, _client, _runtime_signature
    sig = _signature_from_settings(settings)
    if _daemon is not None and _client is not None and _runtime_signature == sig:
        return
    profile = _profile_from_settings(settings)
    _daemon = HardwarePlaneDaemon(
        enable_local_sensors=bool(profile["enable_local_sensors"]),
        enable_hmi=bool(profile["enable_hmi"]),
        profile=profile,
    )
    remote_sensor_transport = None
    if profile["subordinate_mode"]:
        remote_sensor_transport = JsonRpcUdsClient(str(settings.hardware_plane_remote_uds_socket))
    _client = HardwarePlaneClient(
        _daemon,
        default_timeout_ms=settings.hardware_plane_rpc_timeout_ms,
        remote_sensor_transport=remote_sensor_transport,
        remote_sensor_enabled=bool(profile["subordinate_mode"]),
        runtime_profile=profile,
    )
    _runtime_signature = sig


def get_hardware_plane_daemon() -> HardwarePlaneDaemon:
    """获取守护进程单例 / Get daemon singleton."""
    settings = get_settings()
    _ensure_runtime(settings)
    assert _daemon is not None
    return _daemon


def get_hardware_plane_client() -> HardwarePlaneClient:
    """获取客户端单例 / Get client singleton."""
    settings = get_settings()
    _ensure_runtime(settings)
    assert _client is not None
    return _client


async def start_hardware_plane(settings: Settings | None = None) -> None:
    """启动硬件平面 / Start hardware plane."""
    cfg = settings or get_settings()
    if not cfg.hardware_plane_enabled:
        return
    _ensure_runtime(cfg)
    daemon = get_hardware_plane_daemon()
    await daemon.start()
    profile = describe_hardware_plane_profile(cfg)
    if profile["subordinate_mode"]:
        client = get_hardware_plane_client()
        delegated = await client.sensor_read("sensor.gps")
        if delegated.get("success"):
            logger.info("Delegated sensor link ready / 委托传感器链路就绪")
        else:
            logger.warning(
                "Delegated sensor link not ready / 委托传感器链路未就绪: {}",
                delegated.get("error"),
            )


async def stop_hardware_plane() -> None:
    """停止硬件平面 / Stop hardware plane."""
    daemon = get_hardware_plane_daemon()
    await daemon.stop()

