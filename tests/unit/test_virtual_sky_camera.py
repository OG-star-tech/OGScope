"""虚拟相机的新鲜度、失败与像素契约 / Virtual-camera freshness, failure and pixel contracts."""

import asyncio
import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from ogscope.domain.camera.driver import CapturedArray, FrameBuffer
from ogscope.platform.hardware.virtual_sky_camera import VirtualSkyCamera
from ogscope.web.camera_shared import CameraManager


@pytest.fixture
def source():
    """可注入传输故障的小服务 / Small source with injectable transport faults."""
    state = {"frame_id": 0, "mode": "valid", "stream_id": "first"}
    rgb = np.zeros((64, 64, 3), np.uint8)
    rgb[:, :32] = [255, 0, 0]
    rgb[:, 32:] = [0, 0, 255]
    _, encoded = cv2.imencode(".png", rgb[..., ::-1])

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if state["mode"] == "unavailable":
                self.send_response(503)
                self.end_headers()
                return
            if state["mode"] != "duplicate":
                state["frame_id"] += 1
            metadata = {
                "schema_version": 1,
                "source": "virtual_sky",
                "stream_id": state["stream_id"],
                "frame_id": state["frame_id"],
                "width": 64,
                "height": 64,
                "fov_width_deg": 13.01,
                "request_id": query["request_id"][0],
                "observation_time_utc": query["observation_time_utc"][0],
            }
            if state["mode"] == "old_request":
                metadata["request_id"] = "an-old-request"
            if state["mode"] == "wrong_clock":
                metadata["observation_time_utc"] = "2000-01-01T12:00:00Z"
            self.send_response(200)
            self.send_header("X-Virtual-Eye-Meta", json.dumps(metadata))
            self.end_headers()
            self.wfile.write(
                encoded.tobytes() if state["mode"] != "corrupt" else b"bad image"
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    camera = VirtualSkyCamera(
        {
            "virtual_sky_url": f"http://127.0.0.1:{server.server_port}",
            "width": 64,
            "height": 64,
        }
    )
    assert camera.initialize() and camera.start_capture()
    yield camera, state, rgb
    camera.close()
    server.shutdown()
    server.server_close()


def test_virtual_capture_preserves_rgb_and_observation_provenance(source):
    camera, _, rgb = source
    packet = camera.get_video_frame()
    assert isinstance(packet, FrameBuffer)
    np.testing.assert_array_equal(packet.data, rgb)
    assert packet.metadata["capture_source"] == "virtual_sky"
    assert packet.metadata["virtual_frame"]["frame_id"] == 1
    assert camera.get_camera_info()["synthetic"] is True


@pytest.mark.parametrize(
    "mode", ["old_request", "wrong_clock", "corrupt", "unavailable"]
)
def test_source_failures_never_return_last_good_image(source, mode):
    camera, state, _ = source
    camera.get_video_frame()
    state["mode"] = mode
    with pytest.raises(OSError, match="Virtual sky source unavailable"):
        camera.get_video_frame()
    assert camera.get_camera_info()["source_error"]


def test_duplicate_frames_are_rejected_and_restart_is_explicit(source):
    camera, state, _ = source
    camera.get_video_frame()
    state["mode"] = "duplicate"
    with pytest.raises(OSError, match="out-of-order"):
        camera.get_video_frame()
    state.update(mode="valid", stream_id="restarted", frame_id=0)
    assert (
        camera.get_video_frame().metadata["virtual_frame"]["stream_id"] == "restarted"
    )


def test_fresh_epoch_finishes_only_after_a_successful_new_capture(source):
    camera, state, _ = source
    camera.begin_fresh_capture_epoch()
    assert camera.is_within_fresh_capture_epoch()
    state["mode"] = "unavailable"
    with pytest.raises(OSError):
        camera.get_video_frame()
    assert camera.is_within_fresh_capture_epoch()
    state["mode"] = "valid"
    camera.get_video_frame()
    assert not camera.is_within_fresh_capture_epoch()


def test_manager_keeps_metadata_bound_to_pixels_across_later_reads(source):
    camera, _, _ = source
    manager = CameraManager()
    manager.attach_camera_instance(camera)
    first = manager._read_frame_sync()
    assert isinstance(first, CapturedArray)
    retained = first.copy()
    second = manager._read_frame_sync()
    assert retained.capture_metadata["virtual_frame"]["frame_id"] == 1
    assert second.capture_metadata["virtual_frame"]["frame_id"] == 2
    assert retained.capture_sequence < second.capture_sequence
    assert retained.capture_completed_ts <= second.capture_completed_ts


def test_missing_source_configuration_does_not_enable_a_camera():
    camera = VirtualSkyCamera({})
    assert not camera.initialize()
    assert not camera.start_capture()


@pytest.mark.asyncio
async def test_source_failure_is_not_reported_as_connected(source):
    """已有好帧也不能掩盖当前断源 / A previous good frame must not mask current source loss."""
    camera, state, _ = source
    manager = CameraManager()
    manager.attach_camera_instance(camera)
    manager._read_frame_sync()
    state["mode"] = "unavailable"
    with pytest.raises(OSError):
        camera.get_video_frame()
    status = await manager.status()
    assert status["connected"] is False and status["streaming"] is False
    assert status["error"]


@pytest.mark.asyncio
async def test_active_virtual_analysis_reconnects_after_source_returns(monkeypatch):
    """断源释放驱动后仍可恢复，且不替换成物理驱动 / Reconnect after source loss without selecting physical hardware."""
    from ogscope.core.realtime import service as module
    from ogscope.core.realtime.service import RealtimeSolveService

    service = RealtimeSolveService()
    service.state.running = True
    service._analysis_interval_sec = 0

    class Manager:
        attempts = 0
        reads = 0

        def get_camera_instance(self):
            return SimpleNamespace(is_capturing=True) if self.attempts >= 2 else None

        async def ensure_started(self):
            self.attempts += 1
            if self.attempts == 1:
                raise OSError("source still offline")

        async def get_raw_frame(self):
            self.reads += 1
            service.state.running = False
            return None, 1, 1.0

    manager = Manager()
    monkeypatch.setattr(
        module, "get_settings", lambda: SimpleNamespace(camera_type="virtual_sky")
    )
    await asyncio.wait_for(service._run_loop(manager, -1), timeout=3)
    assert manager.attempts == 2 and manager.reads == 1
