"""相机组合、注入与跨入口占用回归 / Camera composition, injection and cross-entry ownership."""

import ast
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ogscope.application import camera as composition
from ogscope.core.application.core_service import CoreContractService
from ogscope.domain.camera.runtime import CameraCapture, CameraControl, CameraRuntime
from ogscope.domain.camera.services import CameraDomainService


class FakeCapture:
    """无硬件的可观察占用端口 / Observable ownership port without hardware."""

    def __init__(self):
        self.streaming = False
        self.leases = set()
        self.starts = 0
        self.stops = 0

    async def ensure_started(self):
        self.streaming = True
        self.starts += 1

    async def stop(self):
        if self.leases:
            raise RuntimeError("相机有占用 / Camera is busy")
        self.streaming = False
        self.stops += 1

    def lifecycle_status(self):
        return {
            "phase": "active" if self.streaming else "sleeping",
            "preview_consumers": 0,
            "analysis_consumers": 0,
            "recording_consumers": 0,
            "operation_consumers": len(self.leases),
            "idle_shutdown_seconds": 30,
            "analysis_readiness": {},
        }

    def update_operation_lease(self, *, lease_id=None, release=False, ttl_seconds=60):
        if release:
            self.leases.discard(lease_id)
            return {"success": True, "released": True}
        lease_id = lease_id or "test-lease"
        self.leases.add(lease_id)
        return {"success": True, "lease_id": lease_id, "ttl_seconds": ttl_seconds}

    async def status(self):
        return {
            "connected": self.streaming,
            "streaming": self.streaming,
            "recording": False,
            "info": {},
            "lifecycle": self.lifecycle_status(),
        }


class FakeControl:
    """行为替身与采集端口绑定 / Bind control behavior to its capture substitute."""

    def __init__(self, capture):
        self.capture = capture

    async def get_camera_status(self):
        return await self.capture.status()

    async def start_camera(self):
        await self.capture.ensure_started()
        return {"success": True}

    async def stop_camera(self):
        try:
            await self.capture.stop()
        except RuntimeError as exc:
            return {"success": False, "message": str(exc)}
        return {"success": True}


class FakePlane:
    """只记录平面同步，不调用任何设备 / Record plane synchronization without devices."""

    def __init__(self):
        self.calls = []

    async def status_get(self):
        return {"success": True, "data": {"services": {}}}

    async def device_command(self, target, action):
        self.calls.append((target, action))
        return {"success": True}


def make_runtime():
    capture = FakeCapture()
    return CameraRuntime(capture=capture, control=FakeControl(capture))


def test_default_runtime_binds_existing_manager_for_every_consumer():
    from ogscope.core.realtime import realtime_solve_service
    from ogscope.domain.camera import streaming
    from ogscope.domain.camera.runtime import SharedFrame
    from ogscope.domain.camera.services import camera_domain_service
    from ogscope.web import camera_shared
    from ogscope.web.api.debug import services

    runtime = composition.get_camera_runtime()
    assert runtime is camera_domain_service.runtime
    assert runtime.control is services.DebugCameraService
    assert isinstance(runtime.capture, CameraCapture)
    assert isinstance(runtime.control, CameraControl)
    assert runtime.capture is camera_shared.get_camera_manager()
    assert runtime.capture is services.get_camera_manager()
    assert runtime.capture is streaming.get_camera_manager()
    assert runtime.capture is realtime_solve_service._camera_capture()
    assert camera_shared.SharedFrame is SharedFrame


def test_concurrent_first_access_constructs_exactly_one_runtime(monkeypatch):
    from ogscope.platform.adapters import camera_runtime

    barrier = threading.Barrier(8)
    built = []
    runtime = make_runtime()

    def build():
        built.append(runtime)
        return runtime

    def access():
        barrier.wait(timeout=3)
        return composition.get_camera_runtime()

    monkeypatch.setattr(composition, "_runtime", None)
    monkeypatch.setattr(camera_runtime, "build_legacy_camera_runtime", build)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: access(), range(8)))
    assert built == [runtime]
    assert all(result is runtime for result in results)


@pytest.mark.asyncio
async def test_two_injected_core_instances_do_not_share_capture_or_leases():
    left, right = make_runtime(), make_runtime()
    left_plane, right_plane = FakePlane(), FakePlane()
    first = CoreContractService(
        camera=CameraDomainService(left), hardware_client=left_plane
    )
    second = CoreContractService(
        camera=CameraDomainService(right), hardware_client=right_plane
    )
    assert (await first.start_camera())["applied"]["ready"] is True
    first.camera_operation_lease(ttl_seconds=30)
    assert (await second.get_camera_status())["streaming"] is False
    assert right.capture.leases == set()
    assert (await first.stop_camera())["applied"] == {"action": "stop", "busy": True}
    assert left_plane.calls == [("camera", "start")]
    assert right_plane.calls == []
    first.camera_operation_lease(lease_id="test-lease", release=True)
    assert (await first.stop_camera())["success"] is True
    assert left.capture.stops == 1 and right.capture.stops == 0


def test_core_and_dev_http_use_one_runtime_and_share_busy_state(client, monkeypatch):
    from ogscope.core.application import core_service

    runtime, plane = make_runtime(), FakePlane()
    monkeypatch.setattr(composition, "_runtime", runtime)
    monkeypatch.setattr(core_service, "get_hardware_plane_client", lambda: plane)
    assert client.post("/api/core/v1/camera/start").json()["applied"]["ready"] is True
    assert client.get("/api/dev/debug/camera/status").json()["streaming"] is True
    lease = client.post("/api/core/v1/camera/lease", json={}).json()["lease_id"]
    assert client.post("/api/dev/debug/camera/stop").json()["success"] is False
    assert client.post("/api/core/v1/camera/stop").json()["applied"]["busy"] is True
    assert plane.calls == [("camera", "start")]
    client.post("/api/core/v1/camera/lease", json={"lease_id": lease, "release": True})
    assert client.post("/api/dev/debug/camera/stop").json()["success"] is True
    status = client.get("/api/core/v1/camera/status").json()
    assert status["lifecycle"]["operation_consumers"] == 0
    assert status["streaming"] is False
    assert runtime.capture.starts == runtime.capture.stops == 1


def test_core_status_preserves_lifecycle_fields_without_starting_capture(
    client, monkeypatch
):
    """真实默认适配器的状态读取不启动硬件 / The default adapter must observe without starting capture."""
    from ogscope.core.application import core_service

    capture = composition.get_camera_capture()
    start = AsyncMock(side_effect=AssertionError("Unexpected capture start"))
    monkeypatch.setattr(capture, "ensure_started", start)
    monkeypatch.setattr(core_service, "get_hardware_plane_client", FakePlane)
    response = client.get("/api/core/v1/camera/status")
    assert response.status_code == 200
    assert {
        "phase",
        "preview_consumers",
        "analysis_consumers",
        "recording_consumers",
        "operation_consumers",
        "idle_shutdown_seconds",
        "analysis_readiness",
    } <= response.json()["lifecycle"].keys()
    start.assert_not_called()


def test_realtime_can_inject_capture_without_changing_shared_runtime():
    from ogscope.core.realtime.service import RealtimeSolveService

    shared = composition.get_camera_runtime()
    isolated = SimpleNamespace()
    service = RealtimeSolveService(capture=isolated)
    assert service._camera_capture() is isolated
    assert composition.get_camera_runtime() is shared


def test_neutral_ports_and_composition_import_without_loading_web():
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import ogscope.application.camera; "
            "assert not any(name.startswith('ogscope.web') for name in sys.modules)",
        ],
        check=True,
        capture_output=True,
    )


def test_core_and_camera_domain_have_no_direct_camera_implementation_imports():
    root = Path(__file__).resolve().parents[2] / "ogscope"
    paths = list((root / "core").rglob("*.py")) + list(
        (root / "domain/camera").glob("*.py")
    )
    violations = []
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            modules = (
                [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else (
                    [alias.name for alias in node.names]
                    if isinstance(node, ast.Import)
                    else []
                )
            )
            if any(
                module
                in {"ogscope.web.camera_shared", "ogscope.web.api.debug.services"}
                for module in modules
            ):
                violations.append(str(path.relative_to(root)))
    assert violations == []
