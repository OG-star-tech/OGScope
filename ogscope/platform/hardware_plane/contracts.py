"""
共享硬件平面统一契约 / Shared hardware plane contracts.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class CapabilityState(str, Enum):
    """能力状态 / Capability state."""

    AVAILABLE = "available"
    PLANNED = "planned"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class CapabilityKind(str, Enum):
    """能力类别 / Capability kind."""

    CAMERA = "camera"
    SENSOR = "sensor"
    HMI = "hmi"
    SYSTEM = "system"


class PlaneMethod(str, Enum):
    """控制面最小方法集 / Minimal control-plane method set."""

    STATUS_GET = "status.get"
    CAPABILITY_LIST = "capability.list"
    SENSOR_READ = "sensor.read"
    DEVICE_COMMAND = "device.command"
    EVENT_SUBSCRIBE = "event.subscribe"


class PlaneErrorCode(str, Enum):
    """统一错误码 / Unified error codes."""

    BAD_REQUEST = "bad_request"
    NOT_FOUND = "not_found"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    INTERNAL_ERROR = "internal_error"
    UNSUPPORTED = "unsupported"


def ok_payload(data: dict[str, Any] | None = None) -> dict[str, Any]:
    """标准成功载荷 / Standard success payload."""
    return {
        "success": True,
        "error": None,
        "data": data or {},
    }


def error_payload(
    *,
    code: PlaneErrorCode,
    message: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """标准失败载荷 / Standard error payload."""
    return {
        "success": False,
        "error": {
            "code": code.value,
            "message": message,
        },
        "data": data or {},
    }
