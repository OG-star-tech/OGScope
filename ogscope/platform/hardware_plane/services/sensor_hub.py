"""
传感器聚合服务 / Sensor hub service.
"""

from __future__ import annotations

import time
from typing import Any

from ogscope.platform.hardware_plane.contracts import CapabilityState


class SensorHubService:
    """传感器聚合服务（低频轮询默认）/ Sensor hub with low-frequency defaults."""

    name = "sensor-hub"

    def __init__(self) -> None:
        self._running = False
        self._states: dict[str, CapabilityState] = {
            "sensor.gps": CapabilityState.AVAILABLE,
            "sensor.magnetometer": CapabilityState.AVAILABLE,
            "sensor.gyroscope": CapabilityState.PLANNED,
            "sensor.accelerometer": CapabilityState.PLANNED,
            "sensor.light": CapabilityState.AVAILABLE,
        }

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "sensors": {name: state.value for name, state in self._states.items()},
        }

    async def read(self, sensor_name: str) -> dict[str, Any]:
        state = self._states.get(sensor_name, CapabilityState.UNAVAILABLE)
        # 在无硬件环境下保持可测试的稳定返回 / Stable return for non-hardware environments.
        value: dict[str, Any] = {"value": None, "unit": None}
        if sensor_name == "sensor.gps":
            value = {"value": {"lat": None, "lon": None}, "unit": "deg"}
        elif sensor_name == "sensor.magnetometer":
            value = {"value": {"heading": None}, "unit": "deg"}
        elif sensor_name == "sensor.light":
            value = {"value": None, "unit": "lux"}
        return {
            "name": sensor_name,
            "state": state.value,
            "timestamp": time.time(),
            **value,
        }

    async def command(
        self, action: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        _ = payload
        if action == "restart":
            self._running = False
            self._running = True
            return {"accepted": True, "message": "sensor hub restarted"}
        return {"accepted": False, "message": f"unsupported action: {action}"}
