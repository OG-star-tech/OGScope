"""部署选择、回退与状态一致性 / Deployment selection, fallback and status consistency."""

import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from ogscope.config import Settings
from ogscope.config_catalog import build_config_catalog
from ogscope.core.application.core_service import CoreContractService
from ogscope.platform.hardware import bcm2835_isp
from ogscope.platform.hardware.camera import IMX327MIPICamera, create_camera
from ogscope.platform.hardware.v4l2_camera import V4L2RawCamera
from ogscope.web.api.models.schemas import (
    CoreCameraStatusResponse,
    CoreStreamStatusResponse,
)

PROFILES = Path(__file__).resolve().parents[2] / "deploy" / "camera"


@pytest.mark.parametrize(
    "name,backend,processing",
    [
        ("compatibility", "v4l2", "software"),
        ("isp", "v4l2", "auto"),
        ("picamera2", "imx327_mipi", "software"),
    ],
)
def test_shipped_profiles_select_explicit_independent_processing(
    monkeypatch, name, backend, processing
):
    for key in ("OGSCOPE_CAMERA_TYPE", "OGSCOPE_CAMERA_V4L2_PROCESSING"):
        monkeypatch.delenv(key, raising=False)
    settings = Settings(_env_file=PROFILES / f"{name}.env")
    assert settings.camera_type == backend
    assert settings.camera_v4l2_processing == processing
    assert settings.camera_auto_exposure_max_us == 3_000_000
    assert not settings.camera_hardware_transform
    assert settings.preview_encoder == "auto"


@pytest.mark.parametrize("backend", ["imx327_mipi", "picamera2", "libcamera"])
def test_explicit_picamera_selection_survives_new_default(
    tmp_path, monkeypatch, backend
):
    monkeypatch.delenv("OGSCOPE_CAMERA_TYPE", raising=False)
    config = tmp_path / "ogscope.env"
    config.write_text(f"OGSCOPE_CAMERA_TYPE={backend}\n")
    settings = Settings(_env_file=config)
    assert settings.camera_type == "imx327_mipi"


def test_invalid_backend_is_rejected_instead_of_silently_selecting_a_driver():
    with pytest.raises(ValueError, match="Unsupported camera"):
        Settings(camera_type="typo")
    assert isinstance(create_camera({}), V4L2RawCamera)


@pytest.mark.parametrize("mode", ["auto", "bcm2835_isp"])
def test_runtime_isp_failure_reuses_same_frame_and_never_retries_failed_isp(
    monkeypatch, mode
):
    camera = V4L2RawCamera({"v4l2_processing": mode})
    raw = np.zeros((4, 4), dtype=np.uint16)
    rgb = np.zeros((4, 4, 3), dtype=np.uint8)
    camera._capture = SimpleNamespace(read=lambda: (True, raw))
    camera.is_initialized = camera.is_capturing = True
    isp = SimpleNamespace(
        process=Mock(side_effect=OSError("ISP timeout")), close=Mock()
    )
    camera._isp = isp
    monkeypatch.setattr(camera, "_unpack_raw", lambda frame: frame)
    monkeypatch.setattr(camera, "_observe_auto_exposure", Mock())
    monkeypatch.setattr(camera, "_apply_temporal_nr", lambda frame: frame)
    monkeypatch.setattr(camera, "_apply_postprocessing", lambda frame: frame)
    debayer = Mock(return_value=rgb)
    monkeypatch.setattr(camera, "_debayer", debayer)
    first, second = camera.capture_image(), camera.capture_image()
    isp.process.assert_called_once()
    isp.close.assert_called_once()
    processing = camera.get_camera_info()["image_processing"]
    assert processing["error"] == "ISP timeout"
    if mode == "auto":
        assert first is rgb and second is rgb
        assert debayer.call_count == 2
        assert all(call.args[0] is raw for call in debayer.call_args_list)
        assert processing["effective"] == "software"
        assert processing["fallback_active"] is True
    else:
        assert first is None and second is None
        debayer.assert_not_called()
        assert processing["effective"] == "unavailable"
        assert processing["fallback_active"] is False


def test_picamera_reports_libcamera_processing_independent_of_v4l2_policy():
    camera = IMX327MIPICamera({"v4l2_processing": "bcm2835_isp"})
    camera.is_initialized = True
    camera.camera = SimpleNamespace(camera_properties={})
    assert camera.get_camera_info()["image_processing"] == {
        "requested": "libcamera",
        "effective": "libcamera_isp",
        "error": None,
    }


def test_initialization_cleanup_failure_never_silently_falls_back(monkeypatch):
    failure = Mock(side_effect=bcm2835_isp.IspCleanupError("cleanup failed"))
    monkeypatch.setattr(bcm2835_isp, "Bcm2835Isp", failure)
    camera = V4L2RawCamera({"v4l2_processing": "auto"})
    with pytest.raises(bcm2835_isp.IspCleanupError):
        camera._initialize_isp()
    assert camera.requires_service_restart
    assert not camera.close()
    info = camera.get_camera_info()["image_processing"]
    assert info["effective"] == "unavailable" and not info["fallback_active"]


def test_runtime_cleanup_failure_stops_frames_instead_of_using_cpu(monkeypatch):
    camera = V4L2RawCamera({"v4l2_processing": "auto"})
    raw = np.zeros((4, 4), dtype=np.uint16)
    camera.is_initialized = camera.is_capturing = True
    camera._capture = SimpleNamespace(read=lambda: (True, raw), release=Mock())
    camera._isp = SimpleNamespace(
        process=Mock(side_effect=OSError("timeout")),
        close=Mock(side_effect=OSError("DMA busy")),
    )
    monkeypatch.setattr(camera, "_unpack_raw", lambda frame: frame)
    monkeypatch.setattr(camera, "_observe_auto_exposure", Mock())
    monkeypatch.setattr(camera, "_apply_temporal_nr", lambda frame: frame)
    debayer = Mock()
    monkeypatch.setattr(camera, "_debayer", debayer)
    assert camera.capture_image() is None
    assert camera.capture_image() is None
    debayer.assert_not_called()
    assert camera.requires_service_restart and not camera.close()


def test_status_serialization_preserves_backend_and_requested_encoder():
    status = CoreContractService._normalize_camera_status(
        {"configured_backend": "v4l2", "connected": True, "info": {}}
    )
    assert CoreCameraStatusResponse(success=True, **status).configured_backend == "v4l2"
    stream = CoreStreamStatusResponse(
        success=True,
        max_clients=2,
        active_clients=1,
        frame_fetch_timeout_ms=20000,
        target_preview_fps=8,
        preview_encoder="turbojpeg",
        preview_encoder_requested="auto",
    )
    assert stream.model_dump()["preview_encoder_requested"] == "auto"


def test_configuration_catalog_exposes_all_acceleration_choices():
    fields = {
        entry["field"]
        for section in build_config_catalog()["sections"]
        for entry in section["entries"]
    }
    assert {
        "camera_type",
        "camera_rotation",
        "camera_hardware_transform",
        "camera_v4l2_processing",
        "camera_v4l2_isp_input_device",
        "camera_v4l2_isp_output_device",
        "camera_v4l2_isp_timeout_sec",
        "preview_encoder",
        "preview_pipeline_enabled",
        "preview_hardware_encoder_device",
    } <= fields


@pytest.mark.parametrize("selection", [None, "v4l2", "imx327_mipi"])
def test_upgrade_pins_only_implicit_legacy_backend(tmp_path, monkeypatch, selection):
    monkeypatch.delenv("OGSCOPE_CAMERA_TYPE", raising=False)
    config = tmp_path / "ogscope.env"
    content = "OGSCOPE_CAMERA_FPS=10\nOGSCOPE_DATA_DIR=/data/ogscope\n"
    if selection:
        content += f"OGSCOPE_CAMERA_TYPE={selection}\n"
    config.write_text(content)
    script = PROFILES.parents[1] / "scripts" / "boot-config-camera.sh"
    subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; sudo() { "$@"; }; ogscope_pin_legacy_camera_backend "$2"; ogscope_pin_legacy_camera_backend "$2"',
            "profile-test",
            str(script),
            str(config),
        ],
        check=True,
    )
    after = config.read_text()
    assert after.startswith(content)
    assert after.count("OGSCOPE_CAMERA_TYPE=") == 1
    assert f"OGSCOPE_CAMERA_TYPE={selection or 'imx327_mipi'}" in after


def test_upgrade_preserves_explicit_installer_backend_when_file_has_none(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("OGSCOPE_CAMERA_TYPE", "V4L2_RAW")
    config = tmp_path / "ogscope.env"
    config.write_text("OGSCOPE_CAMERA_FPS=10\n")
    script = PROFILES.parents[1] / "scripts" / "boot-config-camera.sh"
    subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; sudo() { "$@"; }; ogscope_pin_legacy_camera_backend "$2"',
            "profile-test",
            str(script),
            str(config),
        ],
        check=True,
    )
    assert "OGSCOPE_CAMERA_TYPE=v4l2\n" in config.read_text()
