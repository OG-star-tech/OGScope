from __future__ import annotations

import pytest

from ogscope.hardware_plane.daemon import HardwarePlaneDaemon


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

