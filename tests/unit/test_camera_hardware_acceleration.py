"""硬件加速的几何、帧所有权与失败回退 / Hardware geometry, frame ownership and failure fallback."""

from __future__ import annotations

import asyncio
import ctypes
import subprocess
import sys
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from ogscope.application.camera_manager import CameraManager
from ogscope.config import Settings
from ogscope.domain.camera.encoding import EncodedImage, HardwarePreviewEncoder
from ogscope.domain.camera.geometry import apply_geometry
from ogscope.platform.hardware import bcm2835_isp, v4l2_buffers
from ogscope.platform.hardware.camera import IMX327MIPICamera
from ogscope.platform.hardware.v4l2_camera import V4L2ControlRange, V4L2RawCamera


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize(
    "wanted", [(False, False), (True, False), (False, True), (True, True)]
)
@pytest.mark.parametrize(
    "applied", [(False, False), (True, False), (False, True), (True, True)]
)
def test_partial_hardware_and_runtime_rotation_preserve_exact_rgb_pixels(
    rotation, wanted, applied
):
    original = np.arange(5 * 8 * 3, dtype=np.uint8).reshape(5, 8, 3)
    expected = np.rot90(original, rotation // 90)
    if wanted[0]:
        expected = expected[:, ::-1]
    if wanted[1]:
        expected = expected[::-1]
    hardware_frame = original
    if applied[0]:
        hardware_frame = hardware_frame[:, ::-1]
    if applied[1]:
        hardware_frame = hardware_frame[::-1]
    actual = apply_geometry(hardware_frame.copy(), rotation, *wanted, applied)
    np.testing.assert_array_equal(actual, expected)
    assert actual.flags.c_contiguous


def test_picamera_uses_configured_transform_not_requested_transform(monkeypatch):
    class Transform:
        def __init__(self, hflip=False, vflip=False):
            self.hflip, self.vflip = hflip, vflip

    monkeypatch.setitem(sys.modules, "libcamera", SimpleNamespace(Transform=Transform))
    camera = IMX327MIPICamera(
        {"rotation": 180, "hardware_transform": True, "lores_enabled": False}
    )
    camera.camera = SimpleNamespace(
        create_video_configuration=lambda **kwargs: kwargs,
        camera_configuration=lambda: {"transform": Transform(hflip=True, vflip=False)},
    )
    config = camera._create_video_configuration()
    assert config["transform"].hflip and config["transform"].vflip
    camera._confirm_hardware_transform()
    assert camera._hardware_flips == (True, False)
    assert camera._transform_error
    source = np.arange(48, dtype=np.uint8).reshape(4, 4, 3)
    result = apply_geometry(
        source[:, ::-1].copy(), camera.rotation, False, False, camera._hardware_flips
    )
    np.testing.assert_array_equal(result, source[::-1, ::-1])


def test_v4l2_rejects_unverified_bayer_order_and_restores_unflipped_sensor(monkeypatch):
    camera = V4L2RawCamera({"rotation": 180, "hardware_transform": True})
    camera._control_ranges = {
        name: V4L2ControlRange(0, 1, 1, 0, 0)
        for name in ["horizontal_flip", "vertical_flip"]
    }
    reads = [
        {"horizontal_flip": 0, "vertical_flip": 0},
        {"horizontal_flip": 1, "vertical_flip": 1},
        {"horizontal_flip": 0, "vertical_flip": 0},
    ]
    monkeypatch.setattr(camera, "_read_controls", lambda *_: reads.pop(0))
    commands = []

    def run(*args):
        commands.extend(args)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(camera, "_run_v4l2", run)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0, stdout="fmt:SBGGR10_1X10/160x120"
        ),
    )
    camera._configure_hardware_transform()
    assert camera._hardware_flips == (False, False)
    assert "Bayer" in camera._transform_error
    assert commands[-1] == "--set-ctrl=horizontal_flip=0,vertical_flip=0"


def test_isp_never_sends_invalid_lens_shading_dma_and_uses_16_bit_black_level(
    monkeypatch,
):
    settings = {}
    isp = bcm2835_isp.Bcm2835Isp.__new__(bcm2835_isp.Bcm2835Isp)
    isp.input = SimpleNamespace(fd=1)
    monkeypatch.setattr(
        bcm2835_isp, "set_controls", lambda _fd, values: settings.update(values)
    )
    isp._configure_signal(12, 240, 4095, 2.2)
    assert 0x009819E2 not in settings
    import struct

    assert struct.unpack("=IHHH2x", settings[0x009819E3]) == (1, 3840, 3840, 3840)
    assert len(settings[0x009819E5]) == 136
    assert len(settings[0x009819E1]) == 88
    assert struct.unpack("=IIiI", settings[0x009819E4])[-1] == 1
    assert struct.unpack("=IIiIiI", settings[0x009819E6])[3::2] == (1, 1)
    assert struct.unpack("=IiIiIiI", settings[0x009819E7])[2::2] == (1, 1, 1)


def test_lens_shading_invalid_dma_is_rejected_before_ioctl(monkeypatch):
    called = Mock(side_effect=AssertionError("unsafe ioctl"))
    monkeypatch.setattr(bcm2835_isp, "ioctl", called)
    with pytest.raises(ValueError, match="DMA"):
        bcm2835_isp.set_controls(1, {0x009819E2: bytes(36)})
    called.assert_not_called()


def test_isp_failure_policy_distinguishes_auto_from_required(monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise OSError("ISP busy")

    monkeypatch.setattr(bcm2835_isp, "Bcm2835Isp", unavailable)
    auto = V4L2RawCamera({"v4l2_processing": "auto"})
    auto._initialize_isp()
    assert auto._isp is None and auto._isp_error == "ISP busy"
    required = V4L2RawCamera({"v4l2_processing": "bcm2835_isp"})
    with pytest.raises(OSError, match="busy"):
        required._initialize_isp()


def test_isp_partial_open_failure_releases_input_node(monkeypatch):
    monkeypatch.setattr(bcm2835_isp, "verify_isp_pair", lambda *_: None)
    first = SimpleNamespace(close=Mock())
    calls = []

    def queue(*args):
        calls.append(args)
        if len(calls) == 1:
            return first
        raise OSError("output busy")

    monkeypatch.setattr(bcm2835_isp, "V4L2Queue", queue)
    with pytest.raises(OSError, match="output busy"):
        bcm2835_isp.Bcm2835Isp(
            160,
            120,
            pattern="RGGB",
            bit_depth=12,
            black=240,
            white=4095,
            gamma=2.2,
            input_device="input",
            output_device="output",
        )
    first.close.assert_called_once()


def test_capture_initialization_failure_closes_camera_after_sensor_transform(
    monkeypatch,
):
    camera = V4L2RawCamera({"hardware_transform": True})
    for name in [
        "_configure_media_pipeline",
        "_discover_control_ranges",
        "_apply_exposure_gain",
    ]:
        monkeypatch.setattr(camera, name, lambda *_: True)
    for name in [
        "_configure_hardware_transform",
        "_resolve_line_duration",
        "_resolve_signal_levels",
    ]:
        monkeypatch.setattr(camera, name, lambda: None)
    monkeypatch.setattr(camera, "_create_capture", lambda: None)
    closed = Mock(return_value=True)
    monkeypatch.setattr(camera, "close", closed)
    assert not camera.initialize()
    closed.assert_called_once()


def test_camera_restores_sensor_flips_even_when_isp_close_fails(monkeypatch):
    camera = V4L2RawCamera({})
    camera._original_sensor_flips = {"horizontal_flip": 0, "vertical_flip": 0}
    camera._isp = SimpleNamespace(close=Mock(side_effect=OSError("close failed")))
    commands = []
    monkeypatch.setattr(
        camera,
        "_run_v4l2",
        lambda command: commands.append(command) or SimpleNamespace(returncode=0),
    )
    monkeypatch.setattr(
        camera, "_read_controls", lambda *_: {"horizontal_flip": 0, "vertical_flip": 0}
    )
    assert camera.close() is False
    assert commands == ["--set-ctrl=horizontal_flip=0,vertical_flip=0"]
    assert camera._isp is None and camera._original_sensor_flips is None


def test_kernel_oops_guard_stops_before_opening_a_hardware_node(monkeypatch):
    monkeypatch.setattr(v4l2_buffers.sys, "platform", "linux")
    monkeypatch.setattr(
        v4l2_buffers,
        "Path",
        lambda *_: SimpleNamespace(exists=lambda: True, read_text=lambda: "128"),
    )
    opened = Mock(side_effect=AssertionError("hardware must not open after Oops"))
    monkeypatch.setattr(v4l2_buffers.os, "open", opened)
    with pytest.raises(OSError, match="reboot"):
        v4l2_buffers.V4L2Queue("/dev/unsafe", 2, "bcm2835-isp")
    opened.assert_not_called()


def test_v4l2_abi_and_strided_input_padding():
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        assert ctypes.sizeof(v4l2_buffers.Format) == 208
        assert ctypes.sizeof(v4l2_buffers.Buffer) == 88
        assert ctypes.sizeof(v4l2_buffers._Plane) == 64
    queue = v4l2_buffers.V4L2Queue.__new__(v4l2_buffers.V4L2Queue)
    queue.format = v4l2_buffers.PixelFormat(width=3, height=2, bytesperline=16)
    queue.buffers = [bytearray(32)]
    frame = np.arange(9, dtype=np.uint16).reshape(3, 3)[::2]
    assert queue.write(frame, 1) == 32
    np.testing.assert_array_equal(
        np.frombuffer(queue.buffers[0], dtype=np.uint16).reshape(2, 8)[:, :3], frame
    )
    with pytest.raises(ValueError, match="layout"):
        queue.write(np.zeros((5, 3), dtype=np.uint16), 1)


def test_hardware_encoder_fallback_uses_same_rgb_frame_and_does_not_retry(monkeypatch):
    import ogscope.platform.hardware.v4l2_mjpeg as module

    calls = []

    def unavailable(*_args, **_kwargs):
        calls.append(True)
        raise OSError("codec node missing")

    monkeypatch.setattr(module, "HardwareMjpeg", unavailable)
    encoder = HardwarePreviewEncoder()
    frame = np.zeros((16, 24, 3), dtype=np.uint8)
    frame[:, :, 0] = 250
    for _ in range(2):
        encoded = encoder.encode_jpeg(frame, quality=75)
        assert encoded.encoder in {"opencv", "turbojpeg"}
        bgr = cv2.imdecode(
            np.frombuffer(encoded.data, dtype=np.uint8), cv2.IMREAD_COLOR
        )
        assert bgr[:, :, 2].mean() > 220 and bgr[:, :, 0].mean() < 20
    assert len(calls) == 1 and encoder.error == "codec node missing"


def test_quality_variant_does_not_close_or_reconfigure_active_hardware_encoder():
    encoder = HardwarePreviewEncoder()
    hardware = SimpleNamespace(
        close=Mock(side_effect=AssertionError("active stream must remain configured"))
    )
    encoder._hardware = hardware
    encoder._layout = (24, 16, "RGB888", 75)
    frame = np.zeros((16, 24, 3), dtype=np.uint8)
    frame[:, :, 2] = 250
    result = encoder.encode_variant(frame, quality=55, source_format="RGB888")
    assert result is not None and result.encoder != "v4l2_mjpeg"
    assert encoder._hardware is hardware
    assert encoder._layout == (24, 16, "RGB888", 75)
    hardware.close.assert_not_called()


def test_isp_returns_owned_rgb_before_reusing_padded_dma_output(monkeypatch):
    raw = np.full((2, 3), 500, dtype=np.uint16)
    storage = bytearray(32)
    view = np.ndarray((2, 3, 3), dtype=np.uint8, buffer=storage, strides=(16, 3, 1))
    view[:] = [220, 30, 10]
    isp = bcm2835_isp.Bcm2835Isp.__new__(bcm2835_isp.Bcm2835Isp)
    isp.input = SimpleNamespace(
        fd=1,
        streaming=True,
        write=lambda frame, _channels: frame.nbytes,
        queue=Mock(),
        dequeue=lambda _deadline: None,
    )
    isp.output = SimpleNamespace(
        format=SimpleNamespace(height=2, width=3, bytesperline=16),
        buffers=[storage],
        dequeue=lambda _deadline: v4l2_buffers.Buffer(
            index=0,
            bytesused=32,
            flags=0x4000,
            timestamp=v4l2_buffers._Timeval(*divmod(isp._last_token, 1_000_000)),
        ),
        queue=Mock(),
    )
    isp._gains = (1.0, 1.0, 1.0)
    isp.frames, isp.timeout = 0, 1
    first = isp.process(raw, (1.0, 1.0, 1.0))
    view[:] = [10, 30, 220]
    second = isp.process(raw, (1.0, 1.0, 1.0))
    np.testing.assert_array_equal(first[0, 0], [220, 30, 10])
    np.testing.assert_array_equal(second[0, 0], [10, 30, 220])
    assert first.flags.c_contiguous and not np.shares_memory(first, view)
    assert isp.frames == 2


@pytest.mark.parametrize(
    "flags,echo", [(0x4000, 1_234_567), (0x2000, 1_234_567), (0x4000, 1_234_566)]
)
def test_hardware_frame_token_rejects_old_frames_and_noncopy_clocks(flags, echo):
    buffer = v4l2_buffers.Buffer(
        flags=flags, timestamp=v4l2_buffers._Timeval(*divmod(echo, 1_000_000))
    )
    if flags == 0x4000 and echo == 1_234_567:
        v4l2_buffers.require_frame_token(buffer, 1_234_567)
    else:
        with pytest.raises(OSError, match="current input frame"):
            v4l2_buffers.require_frame_token(buffer, 1_234_567)


def test_output_queue_passes_microsecond_token_in_native_timeval(monkeypatch):
    queue = v4l2_buffers.V4L2Queue.__new__(v4l2_buffers.V4L2Queue)
    queue.type, queue.fd = 2, 7
    queue.capture = queue.multiplane = False
    queued = []
    monkeypatch.setattr(
        v4l2_buffers, "ioctl", lambda _fd, _number, buf: queued.append(buf)
    )
    queue.queue(0, 12, timestamp_us=1_234_567)
    assert queued[0].timestamp.seconds == 1
    assert queued[0].timestamp.microseconds == 234_567
    assert queued[0].bytesused == 12
    queue.capture = True
    with pytest.raises(ValueError):
        queue.queue(0, timestamp_us=1)
    assert len(queued) == 1


def test_isp_rejects_old_output_before_publishing_pixels():
    isp = bcm2835_isp.Bcm2835Isp.__new__(bcm2835_isp.Bcm2835Isp)
    isp.input = SimpleNamespace(
        streaming=True,
        write=lambda frame, _channels: frame.nbytes,
        queue=Mock(),
        dequeue=lambda _deadline: None,
    )
    isp.output = SimpleNamespace(
        dequeue=lambda _deadline: v4l2_buffers.Buffer(flags=0x4000)
    )
    isp._gains, isp.frames, isp.timeout = (1.0, 1.0, 1.0), 0, 1
    with pytest.raises(OSError, match="current input frame"):
        isp.process(np.zeros((2, 3), dtype=np.uint16), (1.0, 1.0, 1.0))
    assert isp.frames == 0


@pytest.mark.parametrize("backend", [bcm2835_isp.Bcm2835Isp, "mjpeg"])
def test_hardware_cleanup_releases_second_queue_after_first_queue_fails(backend):
    if backend == "mjpeg":
        from ogscope.platform.hardware.v4l2_mjpeg import HardwareMjpeg

        backend = HardwareMjpeg
    hardware = backend.__new__(backend)
    hardware.input = SimpleNamespace(
        close=Mock(side_effect=BufferError("exported mapping"))
    )
    output = SimpleNamespace(close=Mock())
    hardware.output = output
    with pytest.raises(BufferError):
        hardware.close()
    output.close.assert_called_once()
    assert hardware.input is hardware.output is None


def test_queue_cleanup_closes_all_mappings_and_fd_even_when_one_mapping_fails(
    monkeypatch,
):
    queue = v4l2_buffers.V4L2Queue.__new__(v4l2_buffers.V4L2Queue)
    queue.fd, queue.type, queue.streaming = 7, 2, False
    good = SimpleNamespace(close=Mock())
    queue.buffers = [
        SimpleNamespace(close=Mock(side_effect=BufferError("exported mapping"))),
        good,
    ]
    closed = []
    monkeypatch.setattr(v4l2_buffers, "ioctl", lambda *_: None)
    monkeypatch.setattr(v4l2_buffers.os, "close", closed.append)
    with pytest.raises(BufferError):
        queue.close()
    good.close.assert_called_once()
    assert closed == [7] and queue.fd == -1 and queue.buffers == []


def test_encoder_cleanup_failure_still_falls_back_on_current_frame(monkeypatch):
    import ogscope.platform.hardware.v4l2_mjpeg as module

    hardware = SimpleNamespace(
        encode=Mock(side_effect=OSError("stale frame token")),
        close=Mock(side_effect=BufferError("exported mapping")),
    )
    monkeypatch.setattr(module, "HardwareMjpeg", lambda *_args, **_kwargs: hardware)
    encoder = HardwarePreviewEncoder()
    frame = np.zeros((16, 24, 3), dtype=np.uint8)
    frame[:, :, 0] = 250
    encoded = encoder.encode_jpeg(frame)
    assert encoded is not None and encoder._hardware is None
    decoded = cv2.imdecode(
        np.frombuffer(encoded.data, dtype=np.uint8), cv2.IMREAD_COLOR
    )
    assert decoded[:, :, 2].mean() > 220 and decoded[:, :, 0].mean() < 20


def test_invalid_isp_parameters_are_rejected_before_native_controls(monkeypatch):
    called = Mock(
        side_effect=AssertionError("invalid controls must not reach the kernel")
    )
    monkeypatch.setattr(bcm2835_isp, "ioctl", called)
    with pytest.raises(ValueError, match="overflow"):
        bcm2835_isp.set_controls(1, {0x009F0905: 1 << 32})
    with pytest.raises(ValueError, match="gamma"):
        bcm2835_isp.Bcm2835Isp(
            160,
            120,
            pattern="RGGB",
            bit_depth=12,
            black=240,
            white=4095,
            gamma=0,
            input_device="input",
            output_device="output",
        )
    called.assert_not_called()


@pytest.mark.asyncio
async def test_preview_overlap_is_bounded_and_cancel_drains_workers():
    manager = CameraManager()
    manager._preview_pipeline_enabled = True
    manager._target_fps = 30
    manager._jpeg_encode_ms.append(40)
    manager._camera_read_ms.append(20)
    encoding_started, release_encoding, second_read = Event(), Event(), Event()
    reads = []

    def read():
        reads.append(len(reads) + 1)
        if len(reads) == 2:
            second_read.set()
        return np.full((4, 6, 3), reads[-1], dtype=np.uint8)

    def encode(frame):
        encoding_started.set()
        assert release_encoding.wait(2)
        return EncodedImage(bytes([int(frame[0, 0, 0])]), "test", "RGB888")

    manager._read_frame_sync = read
    manager._encode_preview_jpeg_sync = encode
    manager._grabber_task = asyncio.create_task(manager._grabber_loop())
    try:
        assert await asyncio.to_thread(encoding_started.wait, 1)
        assert await asyncio.to_thread(second_read.wait, 1)
        assert reads == [1, 2]
        stopped = asyncio.create_task(manager._stop_grabber_locked())
        await asyncio.sleep(0)
        release_encoding.set()
        assert await stopped
        assert manager._inflight_read_future is None
        assert manager._inflight_encode_future is None
        assert manager._latest_jpeg is None
        assert reads == [1, 2]
    finally:
        release_encoding.set()
        if manager._grabber_task:
            await manager._stop_grabber_locked()
        manager._capture_executor.shutdown(wait=True)
        manager._jpeg_executor.shutdown(wait=True)


def test_experimental_acceleration_defaults_are_off_and_invalid_policy_rejected():
    settings = Settings()
    assert settings.camera_rotation == 180
    assert not settings.camera_hardware_transform
    assert not settings.preview_pipeline_enabled
    assert settings.camera_v4l2_processing == "software"
    with pytest.raises(ValueError):
        Settings(camera_v4l2_processing="guess")
    with pytest.raises(ValueError):
        Settings(camera_rotation=45)


@pytest.mark.asyncio
async def test_preview_failure_drains_prefetch_before_camera_close(monkeypatch):
    manager = CameraManager()
    reading, release, finished = Event(), Event(), Event()
    lifecycle = []

    def read():
        reading.set()
        assert release.wait(2)
        finished.set()

    async def lifecycle_step(name, function, timeout):
        assert finished.is_set(), "native camera closed while prefetch was reading"
        lifecycle.append(name)
        return True, False

    async def fail_from_grabber():
        manager._grabber_task = asyncio.current_task()
        await manager._invalidate_camera_locked("failed preview")

    monkeypatch.setattr(manager, "_run_lifecycle_step_locked", lifecycle_step)
    manager._inflight_read_future = asyncio.get_running_loop().run_in_executor(
        manager._capture_executor, read
    )
    try:
        assert await asyncio.to_thread(reading.wait, 1)
        invalidating = asyncio.create_task(fail_from_grabber())
        await asyncio.sleep(0)
        assert not lifecycle
        release.set()
        await invalidating
        assert lifecycle == ["stop", "close"]
        assert manager._inflight_read_future is None
        assert manager._grabber_task is None
    finally:
        release.set()
        manager._capture_executor.shutdown(wait=True)
        manager._jpeg_executor.shutdown(wait=True)
