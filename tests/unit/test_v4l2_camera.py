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
def test_cpu_v4l2_is_the_new_install_default(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        upload_dir=tmp_path / "uploads",
        analysis_dir=tmp_path / "analysis",
    )

    assert settings.camera_type == "v4l2"
    assert settings.camera_v4l2_processing == "software"


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
def test_v4l2_preserves_real_auto_white_balance() -> None:
    camera = V4L2RawCamera({"white_balance_mode": "auto"})

    assert camera.white_balance_mode == "auto"


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
    assert camera.exposure_us == 100_000
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
    assert events[0]["decision"]["exposure_us"] == 100_000
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


@pytest.mark.unit
@pytest.mark.parametrize(
    ("pattern", "red_position", "blue_position"),
    [
        ("RGGB", (0, 0), (1, 1)),
        ("BGGR", (1, 1), (0, 0)),
        ("GRBG", (0, 1), (1, 0)),
        ("GBRG", (1, 0), (0, 1)),
    ],
)
def test_debayer_preserves_asymmetric_red_and_blue_channels(
    pattern: str, red_position: tuple[int, int], blue_position: tuple[int, int]
) -> None:
    """四种真实 CFA 均须输出正确 RGB 通道 / All four physical CFA patterns must produce the correct RGB channels."""
    camera = V4L2RawCamera(
        {
            "v4l2_bayer_pattern": pattern,
            "v4l2_bit_depth": 10,
            "v4l2_gamma": 1.0,
            "white_balance_mode": "manual",
        }
    )
    raw = np.full((8, 8), 256, dtype=np.uint16)
    raw[red_position[0] :: 2, red_position[1] :: 2] = 1023
    raw[blue_position[0] :: 2, blue_position[1] :: 2] = 64

    output = camera._debayer(raw)

    assert np.array_equal(output[2:-2, 2:-2], np.full((4, 4, 3), [255, 64, 16]))


@pytest.mark.unit
@pytest.mark.parametrize(
    ("minimum_lines", "line_duration_us", "expected_minimum_us"),
    [(1, 22.222222, 22), (4, 26.532, 106)],
)
def test_software_ae_minimum_matches_real_sensor_lines(
    minimum_lines: int, line_duration_us: float, expected_minimum_us: int
) -> None:
    """AE 下限与实际控件和回读使用同一行时间换算 / AE minimum uses the same sensor-line conversion as control readback."""
    camera = _ready_camera()
    camera._control_ranges["exposure"] = _control_range(minimum_lines, 300_000)
    camera._line_duration_us = line_duration_us
    camera._ae = camera._create_auto_exposure()

    assert camera._ae.limits.min_exposure_us == expected_minimum_us
    assert camera._ae.limits.exposure_step_us == pytest.approx(line_duration_us)
    assert (
        camera.get_manual_control_ranges()["exposure_us"]["min"] == expected_minimum_us
    )
    assert (
        camera.get_camera_info()["effective_auto_exposure_min_us"]
        == expected_minimum_us
    )


@pytest.mark.unit
def test_software_ae_reaches_sensor_minimum_without_repeated_control_writes(
    monkeypatch,
) -> None:
    """强亮场可从 1ms 降到一行曝光，最低点不重复写控件 / Bright scenes reach one sensor line from 1ms without repeated writes at the limit."""
    camera = _ready_camera()
    monkeypatch.setattr(camera, "_control_frame_ready", lambda: True)
    camera._line_duration_us = 22.222222
    camera._ae = camera._create_auto_exposure()
    writes: dict[str, int] = {}
    write_count = 0

    def _set_control(name: str, value: int) -> bool:
        nonlocal write_count
        writes[name] = value
        write_count += 1
        return True

    monkeypatch.setattr(camera, "_set_control", _set_control)
    monkeypatch.setattr(camera, "_read_controls", lambda *_names: writes.copy())
    assert camera._apply_exposure_gain(1000, 1.0) is True
    raw = np.full((120, 160), 1023, dtype=np.uint16)

    for _ in range(60):
        camera._observe_auto_exposure(raw)

    assert writes["exposure"] == 1
    assert camera.actual_exposure_us == 22
    assert camera.get_camera_info()["ae_state"] == "limited_bright"
    settled_write_count = write_count
    for _ in range(5):
        camera._observe_auto_exposure(raw)
    assert write_count == settled_write_count


@pytest.mark.unit
def test_realtime_default_does_not_blend_moving_scenes() -> None:
    """默认预览输出当前帧，不把旧场景混入新场景 / Default preview passes through current frames without blending old scenes."""
    camera = V4L2RawCamera({})
    old_scene = np.full((4, 4), 1000, dtype=np.uint16)
    new_scene = np.full((4, 4), 2000, dtype=np.uint16)

    camera._apply_temporal_nr(old_scene)
    output = camera._apply_temporal_nr(new_scene)

    assert output is new_scene
    assert camera._nr_accumulator is None
    info = camera.get_camera_info()
    assert info["noise_reduction_mode"] == "off"
    assert info["temporal_noise_reduction"]["enabled"] is False


@pytest.mark.unit
def test_static_temporal_nr_uses_actual_capture_intervals(monkeypatch) -> None:
    """慢速采集不能按传感器帧率放大 EMA 时长 / Slow capture must not stretch EMA duration using sensor FPS."""
    import ogscope.platform.hardware.v4l2_camera as v4l2_camera_module

    clock = {"t": 0.0}
    monkeypatch.setattr(v4l2_camera_module.time, "monotonic", lambda: clock["t"])
    camera = V4L2RawCamera(
        {"v4l2_temporal_nr_alpha": 0.2, "v4l2_temporal_nr_seconds": 2.0}
    )
    camera._frame_duration_us = 16_667
    camera._apply_temporal_nr(np.full((4, 4), 1000, dtype=np.uint16))

    clock["t"] = 0.5
    output = camera._apply_temporal_nr(np.full((4, 4), 2000, dtype=np.uint16))
    assert np.all(output == 1250)
    info = camera.get_camera_info()
    assert info["noise_reduction_mode"] == "temporal"
    assert info["temporal_noise_reduction"]["effective_alpha"] == pytest.approx(0.25)

    clock["t"] = 2.5
    output = camera._apply_temporal_nr(np.full((4, 4), 3000, dtype=np.uint16))
    assert np.all(output == 3000)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("mode", "configured_alpha", "expected_alpha"),
    [
        ("off", 0.2, 1.0),
        ("temporal", 1.0, 0.2),
        ("temporal", 0.3, 0.3),
        ("fast", 0.2, 0.2),
    ],
)
def test_constructor_restores_explicit_noise_reduction_mode(
    mode: str, configured_alpha: float, expected_alpha: float
) -> None:
    """持久化模式重建后仍控制真实混帧行为 / Restored modes continue to control actual frame blending."""
    camera = V4L2RawCamera(
        {
            "noise_reduction_mode": mode,
            "v4l2_temporal_nr_alpha": configured_alpha,
            "v4l2_temporal_nr_seconds": 0.0,
        }
    )
    camera._apply_temporal_nr(np.full((4, 4), 1000, dtype=np.uint16))
    new_scene = np.full((4, 4), 2000, dtype=np.uint16)
    output = camera._apply_temporal_nr(new_scene)

    assert camera.temporal_nr_alpha == expected_alpha
    if expected_alpha == 1.0:
        assert output is new_scene
        assert camera.noise_reduction_mode == "off"
    else:
        assert np.all(output == 1000 + 1000 * expected_alpha)
        assert camera.noise_reduction_mode == "temporal"


@pytest.mark.unit
def test_off_disables_explicit_static_temporal_nr() -> None:
    """关闭降噪必须真正停止跨帧累积 / NR off must actually stop cross-frame accumulation."""
    camera = V4L2RawCamera({"v4l2_temporal_nr_alpha": 0.2})
    camera._apply_temporal_nr(np.full((4, 4), 1000, dtype=np.uint16))

    assert camera.set_noise_reduction_mode("off") is True
    new_scene = np.full((4, 4), 2000, dtype=np.uint16)
    assert camera._apply_temporal_nr(new_scene) is new_scene
    assert camera.get_camera_info()["temporal_noise_reduction"]["enabled"] is False
    assert camera.set_noise_reduction_mode("fast") is False
    assert camera.set_noise_reduction_mode("high_quality") is False
    assert camera.set_noise_reduction_mode("temporal") is True
    assert camera.get_camera_info()["temporal_noise_reduction"]["enabled"] is True


@pytest.mark.unit
def test_temporal_nr_first_frame_is_passthrough() -> None:
    camera = V4L2RawCamera({"v4l2_temporal_nr_alpha": 0.5})
    raw = np.full((4, 4), 1000, dtype=np.uint16)

    output = camera._apply_temporal_nr(raw)

    assert np.array_equal(output, raw)


@pytest.mark.unit
def test_temporal_nr_blends_consecutive_raw_frames_with_configured_alpha() -> None:
    # temporal_nr_seconds=0 pins the fixed alpha, isolating the blend maths
    # from the frame-duration-aware adaptation.
    camera = V4L2RawCamera(
        {"v4l2_temporal_nr_alpha": 0.5, "v4l2_temporal_nr_seconds": 0.0}
    )
    raw_a = np.full((4, 4), 1000, dtype=np.uint16)
    raw_b = np.full((4, 4), 2000, dtype=np.uint16)

    camera._apply_temporal_nr(raw_a)
    output = camera._apply_temporal_nr(raw_b)

    assert np.all(output == 1500)  # 0.5 * 2000 + 0.5 * 1000


@pytest.mark.unit
def test_temporal_nr_keeps_sub_integer_precision_in_raw_domain() -> None:
    """Averaging happens in the linear RAW domain, so the accumulator must
    keep fractional values rather than rounding back to integer RAW codes -
    that sub-integer precision is what the oversampled gamma LUT preserves."""
    camera = V4L2RawCamera(
        {"v4l2_temporal_nr_alpha": 0.5, "v4l2_temporal_nr_seconds": 0.0}
    )
    camera._apply_temporal_nr(np.full((4, 4), 1000, dtype=np.uint16))

    output = camera._apply_temporal_nr(np.full((4, 4), 1001, dtype=np.uint16))

    assert np.allclose(output, 1000.5)


@pytest.mark.unit
def test_temporal_nr_alpha_averages_more_frames_at_short_exposures() -> None:
    """Short exposures deliver many frames per second, so the EMA should
    average far more of them (smaller alpha) than the fixed bound - the
    wall-clock cost is negligible there, unlike at long exposures."""
    camera = V4L2RawCamera(
        {"v4l2_temporal_nr_alpha": 0.2, "v4l2_temporal_nr_seconds": 2.0}
    )

    camera._frame_duration_us = 10_000  # 10ms frames -> 200 in 2s, capped at 50
    assert camera._effective_temporal_nr_alpha() == pytest.approx(1.0 / 50)

    camera._frame_duration_us = 200_000  # 200ms frames -> 10 frames in 2s
    assert camera._effective_temporal_nr_alpha() == pytest.approx(0.1)


@pytest.mark.unit
def test_temporal_nr_alpha_converges_to_no_averaging_at_long_exposures() -> None:
    """A single long exposure already carries its own integration time, so
    forcing extra frames on top of it multiplies the real temporal window
    (and any motion during it) far past what the reported exposure implies.
    Forcing a 5-frame floor at a 3s exposure produced a real 15s blended
    window - invisible on a perfectly still scene, but a source of star
    trailing whenever the mount hasn't fully settled. Long exposures must
    converge to alpha=1 (no extra averaging), not clamp back up to the
    configured alpha."""
    camera = V4L2RawCamera(
        {"v4l2_temporal_nr_alpha": 0.2, "v4l2_temporal_nr_seconds": 2.0}
    )

    camera._frame_duration_us = 3_000_000  # 3s frames -> 0.67 frames in 2s budget

    assert camera._effective_temporal_nr_alpha() == pytest.approx(1.0)


@pytest.mark.unit
def test_temporal_nr_seconds_zero_falls_back_to_fixed_alpha() -> None:
    camera = V4L2RawCamera(
        {"v4l2_temporal_nr_alpha": 0.2, "v4l2_temporal_nr_seconds": 0.0}
    )
    camera._frame_duration_us = 10_000

    assert camera._effective_temporal_nr_alpha() == pytest.approx(0.2)


@pytest.mark.unit
def test_temporal_nr_disabled_at_alpha_one_is_pure_passthrough() -> None:
    camera = V4L2RawCamera({"v4l2_temporal_nr_alpha": 1.0})
    raw_a = np.full((4, 4), 1000, dtype=np.uint16)
    raw_b = np.full((4, 4), 2000, dtype=np.uint16)

    camera._apply_temporal_nr(raw_a)
    output = camera._apply_temporal_nr(raw_b)

    assert np.array_equal(output, raw_b)


@pytest.mark.unit
def test_exposure_change_discards_temporal_nr_history(monkeypatch) -> None:
    """An exposure change must discard the accumulated history (frames at a
    different brightness), but must NOT free the buffer - reallocating a
    full-frame float32 on every AE adjustment walks RSS upward."""
    camera = _ready_camera(v4l2_temporal_nr_alpha=0.5)
    monkeypatch.setattr(camera, "_set_control", lambda _name, _value: True)
    camera._apply_temporal_nr(np.full((120, 160), 42, dtype=np.uint16))
    buffer_before = camera._nr_accumulator

    assert camera._apply_exposure_gain(30_000, 2.0) is True

    assert camera._nr_accumulator_valid is False
    assert camera._nr_accumulator is buffer_before  # buffer kept for reuse

    # The next frame starts fresh rather than blending toward the old value.
    output = camera._apply_temporal_nr(np.full((120, 160), 900, dtype=np.uint16))
    assert np.all(output == 900)


@pytest.mark.unit
def test_start_capture_discards_temporal_nr_history() -> None:
    camera = _ready_camera(v4l2_temporal_nr_alpha=0.5)
    camera._capture = _FakeCapture(np.full((120, 160), 500, dtype=np.uint16))
    camera._apply_temporal_nr(np.full((120, 160), 42, dtype=np.uint16))

    assert camera.start_capture() is True

    assert camera._nr_accumulator_valid is False
    output = camera._apply_temporal_nr(np.full((120, 160), 900, dtype=np.uint16))
    assert np.all(output == 900)


@pytest.mark.unit
def test_fresh_capture_epoch_discards_history_without_reallocating() -> None:
    """Regression for the "still solving a trailed frame" follow-up: preview
    keeps capturing through a mount move (continuous frames at the pre-move
    scene get blended into the EMA), and a fresh frame_id after analysis/start
    is not the same guarantee as a frame free of that old history. Simulates
    continuous preview -> mount movement/old frames -> analysis start
    (begin_fresh_capture_epoch) -> first frame containing no previous EMA
    history, and confirms the accumulator buffer itself is kept (RSS fix)."""
    camera = _ready_camera(v4l2_temporal_nr_alpha=0.5)

    # Continuous preview through a mount move: several frames at the
    # pre-settle scene get blended into the EMA accumulator.
    camera._apply_temporal_nr(np.full((120, 160), 42, dtype=np.uint16))
    camera._apply_temporal_nr(np.full((120, 160), 42, dtype=np.uint16))
    buffer_before = camera._nr_accumulator

    # analysis/start begins.
    camera.begin_fresh_capture_epoch()

    assert camera._nr_accumulator_valid is False
    assert camera._nr_accumulator is buffer_before  # buffer kept for reuse

    # The first frame of the new session starts fresh, not blended toward
    # the pre-move scene.
    output = camera._apply_temporal_nr(np.full((120, 160), 900, dtype=np.uint16))
    assert np.all(output == 900)


@pytest.mark.unit
def test_fresh_capture_epoch_rejects_a_seed_still_mid_exposure_at_reset(
    monkeypatch,
) -> None:
    """Regression for "still see a fade between the old and new scene after
    a move": a frame delivered before one full exposure duration has
    elapsed since begin_fresh_capture_epoch() may itself have started
    exposing before the reset (even before the mount stopped), so it can
    already be trailed. It must not be trusted as the persisted seed - the
    accumulator must stay invalid and keep being overwritten (not blended)
    until a frame is guaranteed to have started exposing after the reset."""
    import ogscope.platform.hardware.v4l2_camera as v4l2_camera_module

    clock = {"t": 0.0}
    monkeypatch.setattr(v4l2_camera_module.time, "monotonic", lambda: clock["t"])
    camera = _ready_camera(v4l2_temporal_nr_alpha=0.5, exposure_us=10_000)  # 10ms

    camera.begin_fresh_capture_epoch()

    # A frame delivered immediately (0ms later) may have started exposing
    # before the reset - must not become the trusted seed yet.
    output = camera._apply_temporal_nr(np.full((120, 160), 111, dtype=np.uint16))
    assert np.all(output == 111)
    assert camera._nr_accumulator_valid is False

    # Still within the one-exposure window (5ms of 10ms elapsed) - same story.
    clock["t"] = 0.005
    output = camera._apply_temporal_nr(np.full((120, 160), 222, dtype=np.uint16))
    assert np.all(output == 222)
    assert camera._nr_accumulator_valid is False

    # A full exposure duration has now elapsed - this frame is guaranteed to
    # have started exposing after the reset, so it becomes the trusted seed.
    clock["t"] = 0.010
    output = camera._apply_temporal_nr(np.full((120, 160), 333, dtype=np.uint16))
    assert np.all(output == 333)
    assert camera._nr_accumulator_valid is True

    # From here on, genuinely new frames blend against the real seed as usual.
    blended = camera._apply_temporal_nr(np.full((120, 160), 999, dtype=np.uint16))
    assert np.all(blended > 333) and np.all(blended < 999)


@pytest.mark.unit
def test_is_within_fresh_capture_epoch_reports_the_same_window(monkeypatch) -> None:
    """is_within_fresh_capture_epoch 与失效窗口保持一致 / Must track the same
    window _apply_temporal_nr uses to decide whether to trust a seed.

    A caller retrying at an unchanged pose (no real settle since the last
    attempt) checks this before deciding whether to wait for a brand-new
    frame - it must report False once the window has actually passed, or
    every retry keeps paying a full exposure's wait for nothing."""
    import ogscope.platform.hardware.v4l2_camera as v4l2_camera_module

    clock = {"t": 0.0}
    monkeypatch.setattr(v4l2_camera_module.time, "monotonic", lambda: clock["t"])
    camera = _ready_camera(exposure_us=10_000)  # 10ms

    assert camera.is_within_fresh_capture_epoch() is False  # never reset yet

    camera.begin_fresh_capture_epoch()
    assert camera.is_within_fresh_capture_epoch() is True

    clock["t"] = 0.005
    assert camera.is_within_fresh_capture_epoch() is True  # still mid-exposure

    clock["t"] = 0.010
    assert camera.is_within_fresh_capture_epoch() is False  # exposure has elapsed


@pytest.mark.unit
def test_black_level_fallback_uses_measured_dark_frame_value_not_zero(
    monkeypatch,
) -> None:
    """No sensor black_level control (confirmed via v4l2-ctl --list-ctrls on
    real hardware) must not silently fall back to 0 - that means zero
    black-level correction is ever applied. Falls back to a value measured
    with the lens covered on real hardware instead."""
    camera = V4L2RawCamera({"v4l2_bit_depth": 12})
    monkeypatch.setattr(camera, "_read_control", lambda _name: None)

    camera._resolve_signal_levels()

    assert camera.black_level != 0
    from ogscope.platform.hardware.v4l2_camera import (
        FALLBACK_BLACK_LEVEL_FRACTION_OF_FULL_RANGE,
    )

    expected = round(FALLBACK_BLACK_LEVEL_FRACTION_OF_FULL_RANGE * 4095)
    assert camera.black_level == expected
    assert camera._signal_level_sources["black_level"] == "fallback_measured_dark_frame"


@pytest.mark.unit
@pytest.mark.parametrize("bit_depth", [10, 12, 16])
def test_linear_pipeline_preserves_full_supported_raw_range(bit_depth) -> None:
    """各位深均保留黑白端点，不溢出索引 / Preserve black/white endpoints at all depths."""
    camera = V4L2RawCamera(
        {"v4l2_bit_depth": bit_depth, "white_balance_mode": "manual"}
    )
    for code, expected in [(0, 0), ((1 << bit_depth) - 1, 255)]:
        output = camera._debayer(np.full((8, 8), code, dtype=np.uint16))
        assert np.all(output == expected)


@pytest.mark.unit
def test_white_balance_is_linear_before_gamma_and_not_applied_twice() -> None:
    """线性增益必须在 gamma 前生效，后处理不重复增益 / Apply gains before gamma, exactly once."""
    camera = V4L2RawCamera(
        {
            "v4l2_bit_depth": 12,
            "white_balance_mode": "manual",
            "white_balance_gain_r": 2.0,
            "white_balance_gain_b": 0.5,
            "width": 160,
            "height": 120,
            "rotation": 0,
        }
    )
    raw = np.full((120, 160), 512, dtype=np.uint16)
    rgb = camera._debayer(raw)
    expected = np.rint((np.array([1024, 512, 256]) / 4095) ** (1 / 2.2) * 255)
    assert np.max(np.abs(rgb[4, 4].astype(float) - expected)) <= 1
    assert np.array_equal(camera._apply_postprocessing(rgb), rgb)


@pytest.mark.unit
def test_linear_lut_rebuilds_when_white_balance_changes() -> None:
    camera = V4L2RawCamera({"white_balance_mode": "manual"})
    raw = np.full((8, 8), 128, dtype=np.uint16)
    first = camera._debayer(raw).copy()
    camera.set_white_balance("manual", 2.0, 0.5)
    second = camera._debayer(raw)
    assert np.all(second[2:-2, 2:-2, 0] > first[2:-2, 2:-2, 0])
    assert np.all(second[2:-2, 2:-2, 2] < first[2:-2, 2:-2, 2])


@pytest.mark.unit
def test_saturation_still_applies_via_float_path() -> None:
    """Saturation is cross-channel so it cannot fold into the LUT; it must
    still take effect rather than being silently dropped."""
    camera = V4L2RawCamera(
        {
            "v4l2_active_width": 160,
            "v4l2_active_height": 120,
            "width": 160,
            "height": 120,
            "rotation": 0,
            "white_balance_mode": "auto",
            "saturation": 0.0,  # fully desaturated -> all channels equal
        }
    )
    image = np.zeros((120, 160, 3), dtype=np.uint8)
    image[..., 0] = 200
    image[..., 2] = 50

    output = camera._apply_postprocessing(image)

    assert output[0, 0, 0] == output[0, 0, 1] == output[0, 0, 2]


@pytest.mark.unit
def test_v4l2_ae_response_setting_reaches_controller_and_telemetry() -> None:
    camera = _ready_camera(v4l2_ae_max_step_stops=1.5)
    assert camera._ae.limits.max_step_stops == 1.5
    assert camera.get_camera_info()["ae_policy"] == {
        "version": "adaptive-raw-v2",
        "max_step_stops": 1.5,
        "fast_step_stops": 4.0,
        "probe_exposure_us": 100_000,
        "settle_frames": 2,
        "settle_policy": "two_queued_frames_plus_old_and_new_frame_duration",
        "filter_reset_on_control_change": True,
    }


@pytest.mark.unit
def test_control_settling_covers_old_long_integration_and_two_queued_frames(
    monkeypatch,
):
    """缩短曝光仍须等旧长帧完成；耗时处理也不使排队帧变新 / Cover old integration and discard queued data."""
    import ogscope.platform.hardware.v4l2_camera as module

    clock = {"t": 10.0}
    monkeypatch.setattr(module.time, "monotonic", lambda: clock["t"])
    camera = _ready_camera(exposure_us=3_000_000)
    camera._frame_duration_us = 3_000_000
    writes = {}
    monkeypatch.setattr(
        camera, "_set_control", lambda name, value: writes.update({name: value}) or True
    )
    monkeypatch.setattr(camera, "_read_controls", lambda *_names: writes.copy())
    assert camera._apply_exposure_gain(10_000, 1)
    assert camera._control_frame_ready() is False
    clock["t"] = 12.9
    assert camera._control_frame_ready() is False
    clock["t"] = 13.1
    assert camera._control_frame_ready() is True
    camera._control_discard_remaining = 1
    assert camera._control_frame_ready() is False
    assert camera._control_frame_ready() is True


@pytest.mark.unit
def test_capture_loop_converges_with_two_real_queued_exposure_frames(monkeypatch):
    """控制回读先变化而队列保留两帧旧图像时仍稳定 / Remain stable when readback leads images by two frames."""
    from collections import deque

    import ogscope.platform.hardware.v4l2_camera as module

    clock = {"t": 0.0}
    monkeypatch.setattr(module.time, "monotonic", lambda: clock["t"])
    camera = _ready_camera()
    camera._ae = camera._create_auto_exposure()
    writes = {}
    monkeypatch.setattr(
        camera, "_set_control", lambda n, v: writes.update({n: v}) or True
    )
    monkeypatch.setattr(camera, "_read_controls", lambda *_names: writes.copy())
    pending = deque([10_000.0] * 2)
    target = 200.0
    desired_signal = 0.12**0.35 * 0.8**0.65
    stable = 0
    for _ in range(80):
        clock["t"] += 0.25
        signal = min(1.0, pending.popleft() / target * desired_signal)
        raw = np.full((120, 160), round(1023 * signal), dtype=np.uint16)
        camera._observe_auto_exposure(raw)
        pending.append(camera.exposure_us * camera.analogue_gain)
        stable = stable + 1 if camera._last_ae["state"] == "converged" else 0
        if stable >= 8:
            break
    assert stable >= 8
    assert camera.exposure_us * camera.analogue_gain == pytest.approx(target, rel=0.1)
    assert clock["t"] < 8


@pytest.mark.unit
@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize(
    "flip_h,flip_v", [(False, False), (True, False), (False, True), (True, True)]
)
def test_rotation_and_flips_preserve_original_pixel_coordinates(
    rotation, flip_h, flip_v
):
    """旋转优化不改变星点坐标、颜色和翻转顺序 / Preserve star coordinates, colors and flip ordering."""
    camera = _ready_camera(
        rotation=rotation, flip_horizontal=flip_h, flip_vertical=flip_v
    )
    source = np.random.default_rng(327).integers(0, 256, (120, 160, 3), dtype=np.uint8)
    expected = np.rot90(source, rotation // 90)
    if flip_h:
        expected = np.fliplr(expected)
    if flip_v:
        expected = np.flipud(expected)
    output = camera._apply_postprocessing(source)
    np.testing.assert_array_equal(output, expected)
    assert output.flags.c_contiguous


@pytest.mark.unit
@pytest.mark.parametrize("gamma", [0.8, 1.0, 2.2, 3.0])
def test_fast_gamma_lookup_is_exact_for_every_16bit_value(gamma):
    """所有 65536 个值与原查表逐值一致 / Every 16-bit value exactly matches the original LUT."""
    camera = _ready_camera(v4l2_gamma=gamma)
    camera._gamma_lut = camera._build_gamma_lut()
    values = np.arange(65536, dtype=np.uint16).reshape(256, 256)
    rgb = np.stack((values, values ^ 65535, np.roll(values, 17)), axis=-1)
    np.testing.assert_array_equal(camera._apply_gamma_lut(rgb), camera._gamma_lut[rgb])


@pytest.mark.unit
def test_gamma_lookup_reuses_workers_but_never_published_frames():
    """尾块与非连续输入不丢像素，后续帧不覆盖先前输出 / Preserve tail/strided pixels and prior outputs."""
    camera = _ready_camera()
    camera._gamma_workers = 4
    camera._gamma_lut = camera._build_gamma_lut()
    rgb = np.random.default_rng(327).integers(0, 65536, (257, 641, 3), dtype=np.uint16)
    first = camera._apply_gamma_lut(rgb)
    saved = first.copy()
    pool = camera._gamma_pool
    second = camera._apply_gamma_lut(rgb[::-1, ::-1])
    assert camera._gamma_pool is pool
    assert pool is not None
    np.testing.assert_array_equal(second, camera._gamma_lut[rgb[::-1, ::-1]])
    np.testing.assert_array_equal(first, saved)
    assert not np.shares_memory(first, second)
    smaller = rgb[:33, :55]
    np.testing.assert_array_equal(
        camera._apply_gamma_lut(smaller), camera._gamma_lut[smaller]
    )


@pytest.mark.unit
def test_gamma_lookup_preserves_single_row_large_width():
    """单行超宽输入仍返回原始值 / Preserve original values for a wide single row."""
    camera = _ready_camera()
    camera._gamma_lut = camera._build_gamma_lut()
    rgb = np.full((1, 11000, 3), 32768, dtype=np.uint16)
    np.testing.assert_array_equal(camera._apply_gamma_lut(rgb), camera._gamma_lut[rgb])


@pytest.mark.unit
@pytest.mark.parametrize("workers", [1, 2, 3, 4])
def test_gamma_workers_close_and_reopen_without_changing_pixels(workers):
    """关闭释放线程，重新取帧仍逐值一致 / Release workers on close and preserve pixels on reuse."""
    camera = _ready_camera()
    camera._gamma_workers = workers
    camera._gamma_lut = camera._build_gamma_lut()
    rgb = np.random.default_rng(7).integers(0, 65536, (129, 131, 3), dtype=np.uint16)
    expected = camera._gamma_lut[rgb]
    np.testing.assert_array_equal(camera._apply_gamma_lut(rgb), expected)
    pool = camera._gamma_pool
    camera.close()
    assert camera._gamma_pool is None
    if pool is not None:
        with pytest.raises(RuntimeError):
            pool.submit(lambda: None)
    np.testing.assert_array_equal(camera._apply_gamma_lut(rgb[::-1]), expected[::-1])
    camera.close()


@pytest.mark.unit
def test_gamma_worker_error_finishes_before_next_frame():
    """错误不能留下未完成写入，下一帧可恢复 / Errors leave no unfinished writes; the next frame recovers."""
    camera = _ready_camera()
    camera._gamma_workers = 4
    camera._gamma_lut = np.arange(16, dtype=np.uint8)
    with pytest.raises(IndexError):
        camera._apply_gamma_lut(np.full((129, 131, 3), 65535, dtype=np.uint16))
    camera._gamma_lut = camera._build_gamma_lut()
    rgb = np.full((129, 131, 3), 32768, dtype=np.uint16)
    np.testing.assert_array_equal(camera._apply_gamma_lut(rgb), camera._gamma_lut[rgb])
    camera.close()


class _QueuedCapture:
    """V4L2 队列替身：每帧带帧起始时间戳与出队等待 / V4L2 queue double: each
    frame has a frame-start stamp (or None) and how long its dequeue waits."""

    def __init__(self, clock: dict[str, float], frames):
        self.clock = clock
        self.frames = list(frames)
        self.current = None
        self.retrieved: list[str] = []
        self.released = False

    def grab(self):
        if not self.frames:
            return False
        self.current = self.frames.pop(0)
        self.clock["t"] += self.current[2]
        return True

    def get(self, prop):
        if prop == cv2.CAP_PROP_POS_MSEC and self.current and self.current[1]:
            return self.current[1] * 1000.0
        return 0.0

    def retrieve(self):
        self.retrieved.append(self.current[0])
        return True, np.full((120, 160), 100, dtype=np.uint16)

    def read(self):
        if not self.grab():
            return False, None
        return self.retrieve()

    def release(self):
        self.released = True


def _settled_camera(monkeypatch, frames):
    """10s 时结算的相机：曝光 50ms，帧周期 100ms / A camera that settled at
    t=10s, with a 50ms exposure and a 100ms frame period."""
    import ogscope.platform.hardware.v4l2_camera as v4l2_camera_module

    clock = {"t": 10.0}
    monkeypatch.setattr(v4l2_camera_module.time, "monotonic", lambda: clock["t"])
    camera = _ready_camera(auto_exposure=False, exposure_us=50_000)
    camera._frame_duration_us = 100_000
    camera._capture = _QueuedCapture(clock, frames)
    camera.begin_fresh_capture_epoch()
    return camera, clock


@pytest.mark.unit
def test_frames_queued_before_a_settle_are_dropped(monkeypatch) -> None:
    """Regression for "the first solve after a move shows the sky before it":
    the camera streams on while no analysis runs, and the frames left in the
    V4L2 queue come out of the first read after a settle looking fresh. Their
    buffer timestamps (frame start) say when they were exposed: only a frame
    whose exposure began after the settle is handed out."""
    camera, _clock = _settled_camera(
        monkeypatch,
        [
            ("before the move", 8.0, 0.0),
            ("during the move", 9.2, 0.0),
            ("exposing at the settle", 10.03, 0.0),  # began at 9.98
            ("after the settle", 10.13, 0.13),  # began at 10.08
            ("next", 10.23, 0.0),
        ],
    )

    assert camera.capture_image() is not None
    assert camera._capture.retrieved == ["after the settle"]
    # Later frames come after a fresh one in the FIFO: no check, no wait.
    assert camera.capture_image() is not None
    assert camera._capture.retrieved == ["after the settle", "next"]


@pytest.mark.unit
def test_without_timestamps_a_waited_for_frame_counts_from_its_completion(
    monkeypatch,
) -> None:
    """No usable buffer timestamp (0, or another clock): a frame the grab
    returned at once was queued, so it is old; a frame it waited for has just
    completed, so it began exposing a frame period plus an exposure ago."""
    camera, _clock = _settled_camera(
        monkeypatch,
        [
            ("queued", None, 0.0),
            ("realtime stamp", 1.79e9, 0.0),  # not CLOCK_MONOTONIC: ignored
            ("in flight", None, 0.06),  # done 10.06, began by 9.91
            ("after the settle", None, 0.1),  # done 10.16, began by 10.01
        ],
    )

    assert camera.capture_image() is not None
    assert camera._capture.retrieved == ["after the settle"]


@pytest.mark.unit
def test_a_retry_without_a_new_settle_takes_the_queued_frame(monkeypatch) -> None:
    """同姿态重试不等新帧 / A retry at an unchanged pose takes what is queued:
    without a settle since the last fresh frame, every queued frame is newer
    than the settle."""
    camera, clock = _settled_camera(monkeypatch, [("after the settle", 10.1, 0.1)])
    camera.capture_image()
    clock["t"] = 30.0
    camera._capture.frames = [("queued while idle", 12.0, 0.0)]

    assert camera.capture_image() is not None
    assert camera._capture.retrieved[-1] == "queued while idle"


@pytest.mark.unit
def test_a_stream_opened_after_the_settle_needs_no_check(monkeypatch) -> None:
    camera, clock = _settled_camera(monkeypatch, [])
    camera.stop_capture()
    reopened = _QueuedCapture(clock, [("first of the new stream", None, 0.0)])
    monkeypatch.setattr(camera, "_create_capture", lambda: reopened)

    assert camera.start_capture() is True
    assert camera.capture_image() is not None
    assert reopened.retrieved == ["first of the new stream"]
