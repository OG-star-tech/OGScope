"""
运行能力注册表 / Runtime capability registry.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import Any

from ogscope.platform.hardware_plane.runtime import get_hardware_plane_client


def _module_available(module_name: str) -> bool:
    """判断模块可用性 / Whether module can be imported."""
    return importlib.util.find_spec(module_name) is not None


@dataclass(slots=True)
class CapabilitySnapshot:
    """能力快照 / Capability snapshot."""

    analysis: bool
    camera: bool
    network: bool

    def to_dict(self) -> dict[str, bool]:
        """转为字典 / Convert to dict."""
        return {
            "analysis": self.analysis,
            "camera": self.camera,
            "network": self.network,
        }


def detect_capabilities() -> CapabilitySnapshot:
    """检测当前运行能力 / Detect runtime capabilities."""
    return CapabilitySnapshot(
        analysis=_module_available("ogscope.domain.analysis.services"),
        camera=_module_available("ogscope.platform.hardware.camera"),
        network=_module_available("ogscope.domain.network.services"),
    )


def capability_map() -> dict[str, Any]:
    """能力字典（兼容序列化）/ Serializable capability map."""
    return detect_capabilities().to_dict()


async def capability_inventory() -> list[dict[str, Any]]:
    """返回硬件平面能力清单 / Return hardware-plane capability inventory."""
    client = get_hardware_plane_client()
    resp = await client.capability_list()
    if not resp.get("success"):
        return []
    data = resp.get("data", {})
    caps = data.get("capabilities", [])
    if isinstance(caps, list):
        return caps
    return []
