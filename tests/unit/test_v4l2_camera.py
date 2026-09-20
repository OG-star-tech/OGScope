"""V4L2 RAW 相机与软件 AE 单元测试 / V4L2 RAW camera and software-AE unit tests."""

from __future__ import annotations

import subprocess

import cv2
import numpy as np
import pytest

import ogscope.config as config_module
from ogscope.config import Settings
from ogscope.domain.camera.ae_diagnostics import load_trace_events
from ogscope.platform.hardware.camera import CameraFactory
from ogscope.platform.hardware.v4l2_camera import (
    V4L2ControlRange,
    V4L2RawCamera,
)
from ogscope.web.camera_shared import CameraManager


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

    def __init__(self, width: int, height: int, fourcc: str | None):
        self.width = width
        self.height = height
        self.fourcc = (
            sum(ord(character) << (8 * index) for index, character in enumerate(fourcc))
            if fourcc
            else 0
        )
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
    config: dict[str, object] = {
        "v4l2_active_width": 160,
        "v4l2_active_height": 120,
        "width": 160,
        "height": 120,
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
@pytest.mark.parametrize("alias", ["v4l2", "V4L2_RAW", "linuxpy_v4l2", "v4l2_linuxpy"])
def test_settings_normalize_v4l2_compatibility_aliases(alias: str) -> None:
    settings = Settings(camera_type=alias)

    assert settings.camera_type == "v4l2"


@pytest.mark.unit
def test_factory_exposes_v4l2_only_when_explicitly_selected() -> None:
    camera = CameraFactory.create_camera("v4l2", {})

    assert isinstance(camera, V4L2RawCamera)
    assert CameraFactory.create_camera("unknown", {}) is None


@pytest.mark.unit
def test_camera_manager_passes_v4l2_board_configuration(monkeypatch, tmp_path) -> None:
    settings = Settings(
        camera_type="v4l2",
        camera_device="/dev/video7",
        camera_v4l2_sensor_subdev="/dev/v4l-subdev4",
        camera_v4l2_media_device="/dev/media2",
        camera_v4l2_sensor_entity="imx327-test",
        camera_v4l2_receiver_entity="csi-test",
        camera_v4l2_sensor_pad=2,
        camera_v4l2_receiver_sink_pad=3,
        camera_v4l2_receiver_source_pad=4,
        data_dir=tmp_path / "data",
        upload_dir=tmp_path / "uploads",
        analysis_dir=tmp_path / "analysis",
    )
    monkeypatch.setattr(config_module, "get_settings", lambda: settings)
    manager = CameraManager.__new__(CameraManager)
    manager._runtime_overrides = {}
    manager._capture_timeout_sec = 8.0

    base = manager._build_base_config()

    assert base["type"] == "v4l2"
    assert base["device"] == "/dev/video7"
    assert base["v4l2_sensor_subdev"] == "/dev/v4l-subdev4"
    assert base["v4l2_media_device"] == "/dev/media2"
    assert base["v4l2_sensor_entity"] == "imx327-test"
    assert base["v4l2_receiver_entity"] == "csi-test"
    assert base["v4l2_sensor_pad"] == 2
    assert base["v4l2_receiver_sink_pad"] == 3
    assert base["v4l2_receiver_source_pad"] == 4
    assert base["v4l2_ae_trace_dir"] == str(tmp_path / "data/camera-ae-traces")


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
def test_capture_accepts_verified_raw_format(monkeypatch) -> None:
    camera = V4L2RawCamera(
        {
            "v4l2_active_width": 1920,
            "v4l2_active_height": 1080,
            "v4l2_pixel_format": "RG10",
        }
    )
    negotiated = _NegotiatedCapture(1920, 1080, "RG10")
    monkeypatch.setattr(cv2, "VideoCapture", lambda *_args: negotiated)

    assert camera._create_capture() is negotiated
    assert negotiated.released is False


@pytest.mark.unit
@pytest.mark.parametrize(
    ("width", "height", "fourcc"),
    [(0, 0, "RG10"), (1920, 1080, None)],
)
def test_capture_rejects_unverifiable_negotiation(
    monkeypatch, width: int, height: int, fourcc: str | None
) -> None:
    camera = V4L2RawCamera(
        {
            "v4l2_active_width": 1920,
            "v4l2_active_height": 1080,
            "v4l2_pixel_format": "RG10",
        }
    )
    negotiated = _NegotiatedCapture(width, height, fourcc)
    monkeypatch.setattr(cv2, "VideoCapture", lambda *_args: negotiated)

    assert camera._create_capture() is None
    assert negotiated.released is True


@pytest.mark.unit
def test_media_pipeline_uses_configured_entities(monkeypatch) -> None:
    camera = V4L2RawCamera(
        {
            "v4l2_media_device": "/dev/media2",
            "v4l2_sensor_entity": "imx327-test",
            "v4l2_receiver_entity": "csi-test",
            "v4l2_sensor_pad": 2,
            "v4l2_receiver_sink_pad": 3,
            "v4l2_receiver_source_pad": 4,
            "v4l2_media_bus_format": "SRGGB10_1X10",
            "v4l2_active_width": 1920,
            "v4l2_active_height": 1080,
        }
    )
    commands: list[list[str]] = []

    def _run(command: list[str], **_kwargs) -> subprocess.CompletedProcess:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", _run)

    assert camera._configure_media_pipeline() is True
    assert camera._media_pipeline["state"] == "configured"
    assert commands == [
        [
            "media-ctl",
            "-d",
            "/dev/media2",
            "--set-v4l2",
            '"imx327-test":2[fmt:SRGGB10_1X10/1920x1080]',
        ],
        [
            "media-ctl",
            "-d",
            "/dev/media2",
            "--set-v4l2",
            '"csi-test":3[fmt:SRGGB10_1X10/1920x1080]',
        ],
        [
            "media-ctl",
            "-d",
            "/dev/media2",
            "--set-v4l2",
            '"csi-test":4[fmt:SRGGB10_1X10/1920x1080]',
        ],
    ]


@pytest.mark.unit
def test_media_pipeline_skips_absent_receiver_pads(monkeypatch) -> None:
    camera = V4L2RawCamera(
        {
            "v4l2_media_device": "/dev/media2",
            "v4l2_sensor_entity": "imx327 10-001a",
            "v4l2_receiver_entity": "unicam-image",
            "v4l2_sensor_pad": 0,
            "v4l2_receiver_sink_pad": -1,
            "v4l2_receiver_source_pad": -1,
        }
    )
    commands: list[list[str]] = []

    def _run(command: list[str], **_kwargs) -> subprocess.CompletedProcess:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", _run)

    assert camera._configure_media_pipeline() is True
    assert commands == [
        [
            "media-ctl",
            "-d",
            "/dev/media2",
            "--set-v4l2",
            '"imx327 10-001a":0[fmt:SRGGB10_1X10/1920x1080]',
        ]
    ]


@pytest.mark.unit
def test_media_pipeline_failure_is_not_silently_ignored(monkeypatch) -> None:
    camera = V4L2RawCamera({})
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 1, "", "bad link"),
    )

    assert camera._configure_media_pipeline() is False
    assert camera._media_pipeline == {
        "enabled": True,
        "state": "error",
        "error": "bad link",
    }


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
def test_control_discovery_rejects_missing_analogue_gain(monkeypatch) -> None:
    camera = V4L2RawCamera({})
    output = """
vertical_blanking 0x009e0901 (int) : min=45 max=261063 step=1 default=45 value=45
exposure 0x009a0902 (int) : min=1 max=262143 step=1 default=100 value=100
"""
    monkeypatch.setattr(
        camera,
        "_run_v4l2",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, output, ""),
    )

    assert camera._discover_control_ranges() is False


@pytest.mark.unit
def test_line_duration_is_derived_from_sensor_controls(monkeypatch) -> None:
    camera = V4L2RawCamera({"v4l2_active_width": 1920, "v4l2_line_duration_us": 0.0})
    values = {"pixel_rate": 275_000_000, "horizontal_blanking": 280}
    monkeypatch.setattr(camera, "_read_control", values.get)

    camera._resolve_line_duration()

    assert camera._line_duration_us == pytest.approx(8.0)
    assert camera._line_duration_source == "sensor_controls"


@pytest.mark.unit
def test_signal_levels_prefer_sensor_controls_and_allow_overrides(monkeypatch) -> None:
    camera = V4L2RawCamera({"v4l2_bit_depth": 10})
    monkeypatch.setattr(
        camera, "_read_control", {"black_level": 64, "white_level": 1000}.get
    )

    camera._resolve_signal_levels()

    assert camera.black_level == 64
    assert camera.white_level == 1000
    assert camera._signal_level_sources["black_level"] == "sensor_control"

    overridden = V4L2RawCamera(
        {"v4l2_bit_depth": 10, "v4l2_black_level": 72, "v4l2_white_level": 980}
    )
    overridden._resolve_signal_levels()
    assert (overridden.black_level, overridden.white_level) == (72, 980)
    assert overridden._signal_level_sources["black_level"] == "config"


@pytest.mark.unit
def test_dark_raw_frame_advances_software_ae(monkeypatch) -> None:
    camera = _ready_camera()
    camera._capture = _FakeCapture(np.full((120, 160), 2, dtype=np.uint16))
    writes: list[tuple[str, int]] = []

    def _record(name: str, value: int) -> bool:
        writes.append((name, value))
        return True

    monkeypatch.setattr(camera, "_set_control", _record)

    frame = camera.capture_image()

    assert frame is not None
    assert frame.shape == (120, 160, 3)
    assert camera.exposure_us == 20_000
    assert camera.get_camera_info()["ae_state"] == "adjusting"
    assert [name for name, _value in writes] == [
        "vertical_blanking",
        "exposure",
        "analogue_gain",
    ]


@pytest.mark.unit
def test_camera_trace_records_observation_decision_and_readback(
    monkeypatch, tmp_path
) -> None:
    camera = _ready_camera(
        v4l2_ae_trace_enabled=True,
        v4l2_ae_trace_dir=str(tmp_path),
        v4l2_ae_trace_raw_sample_interval=1,
    )
    camera._capture = _FakeCapture(np.full((120, 160), 2, dtype=np.uint16))
    camera._trace.start({"test": True})
    monkeypatch.setattr(camera, "_set_control", lambda *_args: True)
    monkeypatch.setattr(
        camera,
        "_read_controls",
        lambda *_names: {
            "exposure": 2_500,
            "analogue_gain": 0,
            "vertical_blanking": 2_480,
        },
    )

    assert camera.capture_image() is not None
    camera.close()

    assert camera._trace.session_dir is not None
    events = load_trace_events(camera._trace.session_dir)
    assert events[0]["observed"]["exposure_us"] == 10_000
    assert events[0]["decision"]["exposure_us"] == 20_000
    assert events[0]["applied"]["actual_exposure_us"] == 20_000
    assert events[0]["applied"]["readback_verified"] is True
    assert events[0]["raw_sample"].startswith("raw/frame-")


@pytest.mark.unit
def test_manual_exposure_disables_software_ae(monkeypatch) -> None:
    camera = _ready_camera()
    monkeypatch.setattr(camera, "_set_control", lambda *_args: True)
    monkeypatch.setattr(
        camera,
        "_read_controls",
        lambda *_names: {
            "exposure": 31_250,
            "analogue_gain": 0,
            "vertical_blanking": 31_230,
        },
    )

    assert camera.set_exposure(250_000) is True

    info = camera.get_camera_info()
    assert info["auto_exposure"] is False
    assert info["ae_state"] == "manual"
    assert info["actual_exposure_us"] == 250_000
    assert info["control_readback"]["verified"] is True


@pytest.mark.unit
def test_failed_control_readback_does_not_claim_actual_values(monkeypatch) -> None:
    camera = _ready_camera()
    monkeypatch.setattr(camera, "_set_control", lambda *_args: True)
    monkeypatch.setattr(camera, "_read_controls", lambda *_names: {})

    assert camera.set_exposure(250_000) is True

    info = camera.get_camera_info()
    assert info["exposure_us"] == 250_000
    assert info["actual_exposure_us"] is None
    assert info["actual_analogue_gain"] is None
    assert info["control_readback"] == {
        "verified": False,
        "error": "missing:analogue_gain,exposure",
    }


@pytest.mark.unit
def test_vblank_expands_dynamic_exposure_range(monkeypatch) -> None:
    camera = _ready_camera()
    camera._control_ranges["exposure"] = _control_range(1, 1_121)
    writes: list[tuple[str, int]] = []

    def _record(name: str, value: int) -> bool:
        writes.append((name, value))
        return True

    monkeypatch.setattr(camera, "_set_control", _record)

    assert camera.set_exposure(2_000_000) is True

    exposure_lines = dict(writes)["exposure"]
    assert exposure_lines == 250_000
    assert exposure_lines > camera._control_ranges["exposure"].maximum


@pytest.mark.unit
def test_v4l2_auto_exposure_ceiling_is_capped_at_three_seconds() -> None:
    """2026-09-20 从 1 秒放宽到 3 秒 - 在真实 Zero2W 上验证 1s-3s 手动曝光后的
    产品决策，见 docs/development/v4l2-zero2w-board-validation.md / Raised
    from 1s to 3s on 2026-09-20 after validating 1s-3s manual exposure on a
    real Zero2W - see docs/development/v4l2-zero2w-board-validation.md."""
    camera = _ready_camera(auto_exposure_max_us=5_000_000)

    assert camera.auto_exposure_max_us == 3_000_000
    assert camera._ae.limits.max_exposure_us == 3_000_000


@pytest.mark.unit
def test_software_ae_gain_limit_respects_hardware_control_range() -> None:
    camera = _ready_camera(v4l2_auto_gain_max=16.0)
    camera._control_ranges["analogue_gain"] = _control_range(0, 20)

    camera._ae = camera._create_auto_exposure()

    assert camera._ae.limits.max_gain == pytest.approx(1.995, abs=0.001)
    assert camera.set_auto_exposure_max_us(5_000_000) is True
    assert camera.auto_exposure_max_us == 3_000_000
    assert camera._ae.limits.max_exposure_us == 3_000_000


@pytest.mark.unit
def test_stop_releases_capture_and_start_reopens_it(monkeypatch) -> None:
    camera = _ready_camera()
    original = _FakeCapture(np.zeros((120, 160), dtype=np.uint16))
    replacement = _FakeCapture(np.zeros((120, 160), dtype=np.uint16))
    camera._capture = original
    monkeypatch.setattr(camera, "_create_capture", lambda: replacement)

    assert camera.stop_capture() is True
    assert original.released is True
    assert camera._capture is None
    assert camera.start_capture() is True
    assert camera._capture is replacement


@pytest.mark.unit
def test_native_crop_and_supersample_report_matching_effective_fov() -> None:
    native = V4L2RawCamera(
        {
            "v4l2_active_width": 1920,
            "v4l2_active_height": 1080,
            "width": 1280,
            "height": 720,
            "sampling_mode": "native",
            "rotation": 180,
        }
    )
    supersample = V4L2RawCamera(
        {
            "v4l2_active_width": 1920,
            "v4l2_active_height": 1080,
            "width": 1280,
            "height": 720,
            "sampling_mode": "supersample",
            "rotation": 180,
        }
    )

    native_fov = native.get_camera_info()["optics"]["effective_fov_deg"]
    supersample_fov = supersample.get_camera_info()["optics"]["effective_fov_deg"]

    assert native_fov["width"] == pytest.approx(13.01)
    assert native_fov["height"] == pytest.approx(7.34)
    assert supersample_fov["width"] == pytest.approx(19.41, abs=0.02)
    assert supersample_fov["height"] == pytest.approx(11.0, abs=0.02)


@pytest.mark.unit
def test_native_postprocessing_center_crops_full_sensor_frame() -> None:
    camera = V4L2RawCamera(
        {
            "v4l2_active_width": 320,
            "v4l2_active_height": 240,
            "width": 160,
            "height": 120,
            "sampling_mode": "native",
            "white_balance_mode": "manual",
            "rotation": 0,
        }
    )
    source = np.arange(320 * 240 * 3, dtype=np.uint8).reshape(240, 320, 3)

    output = camera._apply_postprocessing(source)

    assert output.shape == (120, 160, 3)
    assert np.array_equal(output, source[60:180, 80:240])


@pytest.mark.unit
def test_v4l2_capabilities_truthfully_report_software_ae() -> None:
    camera = _ready_camera()

    info = camera.get_camera_info()

    assert info["capabilities"]["auto_exposure"] is True
    assert info["capabilities"]["software_auto_exposure"] is True
    assert info["capabilities"]["manual_digital_gain"] is False
    assert info["auto_exposure_engine"] == "software_night_sky"
