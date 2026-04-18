"""
硬件平面守护进程（进程内实现） / In-process hardware-plane daemon.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from ogscope.hardware_plane.contracts import (
    CapabilityKind,
    CapabilityState,
    PlaneErrorCode,
    PlaneMethod,
    error_payload,
    ok_payload,
)
from ogscope.hardware_plane.registry import CapabilityRecord, CapabilityRegistry
from ogscope.hardware_plane.services.base import HardwareService
from ogscope.hardware_plane.services.camera_service import CameraPlaneService
from ogscope.hardware_plane.services.hmi import HmiService
from ogscope.hardware_plane.services.sensor_hub import SensorHubService


@dataclass(slots=True)
class StartupPhase:
    """启动阶段 / Startup phase."""

    phase_id: str
    started_at: float
    ended_at: float | None = None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase_id": self.phase_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": (
                int((self.ended_at - self.started_at) * 1000)
                if self.ended_at is not None
                else None
            ),
            "detail": self.detail,
        }


@dataclass(slots=True)
class HardwarePlaneMetrics:
    """运行指标 / Runtime metrics."""

    request_count: int = 0
    error_count: int = 0
    timeout_count: int = 0
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_count": self.request_count,
            "error_count": self.error_count,
            "timeout_count": self.timeout_count,
            "last_error": self.last_error,
        }


class HardwarePlaneDaemon:
    """硬件平面守护进程 / Hardware plane daemon."""

    def __init__(self) -> None:
        self._started = False
        self._started_at: float | None = None
        self._registry = CapabilityRegistry()
        self._metrics = HardwarePlaneMetrics()
        self._phases: list[StartupPhase] = []
        self._services: dict[str, HardwareService] = {
            "camera": CameraPlaneService(),
            "sensor-hub": SensorHubService(),
            "hmi": HmiService(),
        }
        self._register_defaults()

    def _register_defaults(self) -> None:
        self._registry.register(
            CapabilityRecord(
                name="camera.preview",
                kind=CapabilityKind.CAMERA,
                state=CapabilityState.AVAILABLE,
                writable=True,
            )
        )
        self._registry.register(
            CapabilityRecord(
                name="sensor.gps",
                kind=CapabilityKind.SENSOR,
                state=CapabilityState.AVAILABLE,
                writable=False,
            )
        )
        self._registry.register(
            CapabilityRecord(
                name="sensor.magnetometer",
                kind=CapabilityKind.SENSOR,
                state=CapabilityState.AVAILABLE,
                writable=False,
            )
        )
        self._registry.register(
            CapabilityRecord(
                name="sensor.gyroscope",
                kind=CapabilityKind.SENSOR,
                state=CapabilityState.PLANNED,
                writable=False,
            )
        )
        self._registry.register(
            CapabilityRecord(
                name="sensor.accelerometer",
                kind=CapabilityKind.SENSOR,
                state=CapabilityState.PLANNED,
                writable=False,
            )
        )
        self._registry.register(
            CapabilityRecord(
                name="hmi.display",
                kind=CapabilityKind.HMI,
                state=CapabilityState.AVAILABLE,
                writable=True,
            )
        )

    def begin_phase(self, phase_id: str, detail: str = "") -> StartupPhase:
        phase = StartupPhase(phase_id=phase_id, started_at=time.time(), detail=detail)
        self._phases.append(phase)
        return phase

    def end_phase(self, phase: StartupPhase) -> None:
        phase.ended_at = time.time()

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._started_at = time.time()
        phase_p1 = self.begin_phase("P1", "hardware plane ready")
        await self._services["sensor-hub"].start()
        await self._services["hmi"].start()
        self.end_phase(phase_p1)

    async def stop(self) -> None:
        if not self._started:
            return
        await asyncio.gather(*(service.stop() for service in self._services.values()))
        self._started = False

    async def handle_call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        params = params or {}
        self._metrics.request_count += 1
        try:
            if method == PlaneMethod.STATUS_GET.value:
                return ok_payload(await self.status())
            if method == PlaneMethod.CAPABILITY_LIST.value:
                return ok_payload({"capabilities": self._registry.as_dict_list()})
            if method == PlaneMethod.SENSOR_READ.value:
                sensor_name = str(params.get("name", ""))
                return ok_payload(
                    {"sensor": await self._services["sensor-hub"].read(sensor_name)}
                )
            if method == PlaneMethod.DEVICE_COMMAND.value:
                target = str(params.get("target", ""))
                action = str(params.get("action", ""))
                payload = params.get("payload")
                service = self._services.get(target)
                if service is None:
                    return error_payload(
                        code=PlaneErrorCode.NOT_FOUND,
                        message=f"device target not found: {target}",
                    )
                return ok_payload(
                    {
                        "target": target,
                        "action": action,
                        "result": await service.command(action, payload),
                    }
                )
            if method == PlaneMethod.EVENT_SUBSCRIBE.value:
                topic = str(params.get("topic", "hardware.events"))
                return ok_payload(
                    {
                        "topic": topic,
                        "transport": "uds-pubsub-placeholder",
                        "note": "event plane placeholder",
                    }
                )
            return error_payload(
                code=PlaneErrorCode.UNSUPPORTED,
                message=f"unsupported method: {method}",
            )
        except asyncio.TimeoutError:
            self._metrics.timeout_count += 1
            self._metrics.error_count += 1
            self._metrics.last_error = "timeout"
            return error_payload(code=PlaneErrorCode.TIMEOUT, message="call timeout")
        except Exception as exc:  # pragma: no cover - 防御性兜底 / defensive guard
            self._metrics.error_count += 1
            self._metrics.last_error = str(exc)
            return error_payload(
                code=PlaneErrorCode.INTERNAL_ERROR,
                message=f"internal error: {exc}",
            )

    async def status(self) -> dict[str, Any]:
        service_status: dict[str, Any] = {}
        for key, service in self._services.items():
            service_status[key] = await service.status()
        return {
            "started": self._started,
            "started_at": self._started_at,
            "phases": [phase.to_dict() for phase in self._phases],
            "services": service_status,
            "capabilities": self._registry.as_dict_list(),
            "metrics": self._metrics.to_dict(),
        }

    def metrics(self) -> dict[str, Any]:
        return self._metrics.to_dict()

