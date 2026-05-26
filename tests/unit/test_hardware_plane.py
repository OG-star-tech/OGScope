from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from ogscope.platform.hardware_plane.daemon import HardwarePlaneDaemon
from ogscope.platform.hardware_plane.runtime import describe_hardware_plane_profile
from ogscope.platform.hardware_plane.transport.jsonrpc_uds import (
    JsonRpcUdsClient,
    JsonRpcUdsServer,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_hardware_plane_daemon_minimal_methods() -> None:
    daemon = HardwarePlaneDaemon()
    await daemon.start()

    status = await daemon.handle_call("status.get", {})
    assert status["success"] is True
    assert status["data"]["started"] is True

    capabilities = await daemon.handle_call("capability.list", {})
    assert capabilities["success"] is True
    names = [item["name"] for item in capabilities["data"]["capabilities"]]
    assert "sensor.gyroscope" in names

    sensor = await daemon.handle_call("sensor.read", {"name": "sensor.gyroscope"})
    assert sensor["success"] is True
    assert sensor["data"]["sensor"]["state"] == "planned"

    await daemon.stop()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_hardware_plane_daemon_subordinate_profile_disables_local_services() -> (
    None
):
    daemon = HardwarePlaneDaemon(
        enable_local_sensors=False,
        enable_hmi=False,
        profile={
            "role": "subordinate",
            "sensor_source": "remote_delegated",
        },
    )
    await daemon.start()
    status = await daemon.status()
    assert status["started"] is True
    assert status["profile"]["role"] == "subordinate"
    assert set(status["services"].keys()) == {"camera"}
    caps = {item["name"]: item for item in status["capabilities"]}
    assert caps["sensor.gps"]["metadata"]["source"] == "remote_delegated"
    assert "hmi.display" not in caps
    await daemon.stop()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_jsonrpc_uds_sensor_read_roundtrip(tmp_path: Path) -> None:
    _ = tmp_path
    socket_path = (
        Path("/tmp") / f"external-sensor-{os.getpid()}-{int(time.time() * 1000)}.sock"
    )

    async def _handler(method: str, params: dict[str, object]) -> dict[str, object]:
        if method != "sensor.read":
            return {"success": False, "error": {"message": "unsupported"}, "data": {}}
        return {
            "success": True,
            "error": None,
            "data": {
                "sensor": {
                    "name": str(params.get("name", "")),
                    "state": "available",
                    "value": {"heading": 123.4},
                    "unit": "deg",
                }
            },
        }

    server = JsonRpcUdsServer(str(socket_path), _handler)
    await server.start()
    try:
        client = JsonRpcUdsClient(str(socket_path))
        resp = await client.call("sensor.read", {"name": "sensor.magnetometer"})
        assert resp["success"] is True
        assert resp["data"]["sensor"]["name"] == "sensor.magnetometer"
    finally:
        await server.stop()


@pytest.mark.unit
def test_runtime_profile_subordinate_disables_ui_hmi_local_sensors() -> None:
    from ogscope.config import Settings

    profile = describe_hardware_plane_profile(
        Settings(
            hardware_plane_role="subordinate",
            enable_hmi=True,
            enable_ui=True,
            enable_local_sensors=True,
        )
    )
    assert profile["role"] == "subordinate"
    assert profile["sensor_source"] == "remote_delegated"
    assert profile["enable_hmi"] is False
    assert profile["enable_ui"] is True
    assert profile["enable_local_sensors"] is False
