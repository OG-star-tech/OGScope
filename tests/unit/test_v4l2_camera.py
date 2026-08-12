"""V4L2 RAW 相机与软件 AE 单元测试 / V4L2 RAW camera and software-AE unit tests."""

from __future__ import annotations

import subprocess

import cv2
import numpy as np
import pytest

from ogscope.config import Settings
from ogscope.platform.hardware.camera import CameraFactory
from ogscope.platform.hardware.v4l2_camera import (
    V4L2ControlRange,
    V4L2RawCamera,
)


class _FakeCapture:
    """返回固定 RAW 帧的抓帧替身 / Capture double returning a fixed RAW frame."""

    def __init__(self, frame: np.ndarray):
        self.frame = frame
        self.released = False

    def read(self):
        return True, self.frame.copy()

    def release(self) -> None:
        self.released = True


class _NegotiatedCapture:
    """模拟 V4L2 格式协商结果 / Simulate negotiated V4L2 format properties."""

    def __init__(self, width: int, height: int, fourcc: str):
        self.width = width
        self.height = height
        self.fourcc = cv2.VideoWriter_fourcc(*fourcc)
        self.released = False

    def isOpened(self) -> bool:  # noqa: N802 - OpenCV compatibility
        return True

    def set(self, _property: int, _value: float) -> bool:
        return True

    def get(self, property_id: int) -> float:
        if property_id == cv2.CAP_PROP_FRAME_WIDTH:
            return float(self.width)
        if property_id == cv2.CAP_PROP_FRAME_HEIGHT:
            return float(self.height)
        if property_id == cv2.CAP_PROP_FOURCC:
            return float(self.fourcc)
        return 0.0

    def release(self) -> None:
        self.released = True


def _control_range(
    minimum: int, maximum: int, *, default: int = 0, value: int = 0
) -> V4L2ControlRange:
    return V4L2ControlRange(minimum, maximum, 1, default, value)


def _ready_camera(**extra: object) -> V4L2RawCamera:
    config = {
        "v4l2_active_width": 32,
        "v4l2_active_height": 24,
        "width": 32,
        "height": 24,
        "rotation": 0,
        "auto_exposure": True,
        "exposure_us": 10_000,
        "analogue_gain": 1.0,
        "v4l2_line_duration_us": 8.0,
    }
    config.update(extra)
    camera = V4L2RawCamera(config)
    camera._control_ranges = {
        "exposure": _control_range(1, 300_000, default=1_250, value=1_250),
        "analogue_gain": _control_range(0, 98),
        "vertical_blanking": _control_range(4, 300_000, default=45, value=45),
    }
    camera._line_duration_us = 8.0
    camera.is_initialized = True
    camera.is_capturing = True
    return camera


@pytest.mark.unit
def test_picamera2_remains_the_product_default(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        upload_dir=tmp_path / "uploads",
        analysis_dir=tmp_path / "analysis",
    )

    assert settings.camera_type == "imx327_mipi"


@pytest.mark.unit
def test_factory_exposes_v4l2_only_when_explicitly_selected() -> None:
    camera = CameraFactory.create_camera("v4l2", {})

    assert isinstance(camera, V4L2RawCamera)
    assert CameraFactory.create_camera("unknown", {}) is None


@pytest.mark.unit
def test_v4l2_maps_default_auto_white_balance_to_night() -> None:
    camera = V4L2RawCamera({"white_balance_mode": "auto"})

    assert camera.white_balance_mode == "night"


@pytest.mark.unit
def test_capture_rejects_silent_non_raw_fallback(monkeypatch) -> None:
    camera = V4L2RawCamera(
        {
            "v4l2_active_width": 1920,
            "v4l2_active_height": 1080,
            "v4l2_pixel_format": "RG10",
        }
    )
    negotiated = _NegotiatedCapture(1920, 1080, "YUYV")
    monkeypatch.setattr(cv2, "VideoCapture", lambda *_args: negotiated)

    assert camera._create_capture() is None
    assert negotiated.released is True
    assert camera._capture_format["actual_fourcc"] == "YUYV"


@pytest.mark.unit
def test_control_discovery_requires_exposure_and_gain(monkeypatch) -> None:
    camera = V4L2RawCamera({})
    output = """
vertical_blanking 0x009e0901 (int) : min=45 max=261063 step=1 default=45 value=45
exposure 0x009a0902 (int) : min=1 max=262143 step=1 default=100 value=100
analogue_gain 0x009e0903 (int) : min=0 max=98 step=1 default=0 value=0
"""
    monkeypatch.setattr(
        camera,
        "_run_v4l2",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, output, ""),
    )

    assert camera._discover_control_ranges() is True
    assert camera._control_ranges["vertical_blanking"].maximum == 261_063


@pytest.mark.unit
def test_line_duration_is_derived_from_sensor_controls(monkeypatch) -> None:
    camera = V4L2RawCamera({"v4l2_active_width": 1920, "v4l2_line_duration_us": 0.0})
    values = {"pixel_rate": 275_000_000, "horizontal_blanking": 280}
    monkeypatch.setattr(camera, "_read_control", values.get)

    camera._resolve_line_duration()

    assert camera._line_duration_us == pytest.approx(8.0)
    assert camera._line_duration_source == "sensor_controls"


@pytest.mark.unit
def test_dark_raw_frame_advances_software_ae(monkeypatch) -> None:
    camera = _ready_camera()
    camera._capture = _FakeCapture(np.full((24, 32), 2, dtype=np.uint16))
    writes: list[tuple[str, int]] = []

    def _record(name: str, value: int) -> bool:
        writes.append((name, value))
        return True

    monkeypatch.setattr(camera, "_set_control", _record)

    frame = camera.capture_image()

    assert frame is not None
    assert frame.shape == (24, 32, 3)
    assert camera.exposure_us == 20_000
    assert camera.get_camera_info()["ae_state"] == "adjusting"
    assert [name for name, _value in writes] == [
        "vertical_blanking",
        "exposure",
        "analogue_gain",
    ]


@pytest.mark.unit
def test_manual_exposure_disables_software_ae(monkeypatch) -> None:
    camera = _ready_camera()
    monkeypatch.setattr(camera, "_set_control", lambda *_args: True)

    assert camera.set_exposure(250_000) is True

    info = camera.get_camera_info()
    assert info["auto_exposure"] is False
    assert info["ae_state"] == "manual"
    assert info["actual_exposure_us"] == 250_000


@pytest.mark.unit
def test_vblank_expands_dynamic_exposure_range(monkeypatch) -> None:
    camera = _ready_camera()
    camera._control_ranges["exposure"] = _control_range(1, 1_121)
    writes: list[tuple[str, int]] = []
    monkeypatch.setattr(
        camera,
        "_set_control",
        lambda name, value: writes.append((name, value)) or True,
    )

    assert camera.set_exposure(2_000_000) is True

    exposure_lines = dict(writes)["exposure"]
    assert exposure_lines == 250_000
    assert exposure_lines > camera._control_ranges["exposure"].maximum


@pytest.mark.unit
def test_v4l2_capabilities_truthfully_report_software_ae() -> None:
    camera = _ready_camera()

    info = camera.get_camera_info()

    assert info["capabilities"]["auto_exposure"] is True
    assert info["capabilities"]["software_auto_exposure"] is True
    assert info["capabilities"]["manual_digital_gain"] is False
    assert info["auto_exposure_engine"] == "software_night_sky"
