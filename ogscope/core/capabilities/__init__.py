"""
能力检测导出 / Capability exports.
"""

from ogscope.core.capabilities.registry import (
    CapabilitySnapshot,
    capability_inventory,
    capability_map,
    detect_capabilities,
)

__all__ = [
    "CapabilitySnapshot",
    "capability_map",
    "capability_inventory",
    "detect_capabilities",
]
