"""IMX327 产品 tuning 与曝光诊断测试 / IMX327 product tuning and exposure diagnostics tests."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pytest

from ogscope.platform.hardware.camera import IMX327MIPICamera


def _camera(**extra: Any) -> IMX327MIPICamera:
    config: dict[str, Any] = {
        "width": 1280,
        "height": 720,
        "fps": 8,
        "auto_exposure": True,
    }
    config.update(extra)
    return IMX327MIPICamera(config)


@pytest.mark.unit
def test_product_tuning_long_curve_reaches_one_second() -> None:
    """产品曲线优先延长曝光并最终到达 1 秒 / Product curve prioritizes shutter and reaches 1s."""
    with IMX327MIPICamera.PRODUCT_TUNING_FILE.open(encoding="utf-8") as file:
        tuning = json.load(file)

    agc = next(item["rpi.agc"] for item in tuning["algorithms"] if "rpi.agc" in item)
    long_mode = agc["exposure_modes"]["long"]

    assert long_mode["shutter"][-1] == 1_000_000
    assert len(long_mode["shutter"]) == len(long_mode["gain"])
    first_max_shutter = long_mode["shutter"].index(1_000_000)
    assert long_mode["gain"][: first_max_shutter + 1] == [1.0] * (first_max_shutter + 1)
    assert max(long_mode["gain"]) == 4.0
    assert agc["constraint_modes"]["shadows"][0]["q_hi"] == pytest.approx(0.5)


@pytest.mark.unit
def test_autonomous_ae_selects_libcamera_long_shadows_for_starfield(
    monkeypatch,
) -> None:
    """暗场确认后必须请求 Long+Shadows / Confirmed darkness must request Long+Shadows."""

    class Constraint:
        Normal = "constraint-normal"
        Shadows = "constraint-shadows"

    class Metering:
        Matrix = "metering-matrix"

    class Exposure:
        Normal = "exposure-normal"
        Long = "exposure-long"

    class Namespace:
        AeConstraintModeEnum = Constraint
        AeMeteringModeEnum = Metering
        AeExposureModeEnum = Exposure

    class FakeCamera:
        camera_controls = {
            "AeConstraintMode": object(),
            "AeMeteringMode": object(),
            "AeExposureMode": object(),
            "ExposureValue": object(),
            "FrameDurationLimits": object(),
        }

        def __init__(self) -> None:
            self.controls: list[dict[str, Any]] = []

        def set_controls(self, controls: dict[str, Any]) -> None:
            self.controls.append(controls)

    camera = _camera(ae_exposure_value=1.0)
    fake = FakeCamera()
    camera.camera = fake
    monkeypatch.setattr(
        camera,
        "_load_ae_control_namespace",
        lambda: (Namespace, "test.libcamera.controls"),
    )
    dark = {
        "p50": 8.0,
        "p90": 10.0,
        "p99": 12.0,
        "p99_8": 13.0,
        "saturated_fraction": 0.0,
    }

    camera._update_aggressive_auto_exposure(dark)
    camera._ae_last_adjust_at = 0.0
    camera._update_aggressive_auto_exposure(dark)

    scene_update = next(item for item in fake.controls if "AeExposureMode" in item)
    assert camera._ae_scene_mode == "starfield"
    assert scene_update["AeExposureMode"] == "exposure-long"
    assert scene_update["AeConstraintMode"] == "constraint-shadows"
    assert camera._ae_control_backend == "test.libcamera.controls"


@pytest.mark.unit
def test_autonomous_ae_immediately_escapes_severe_brightness(monkeypatch) -> None:
    """严重过曝必须立即退回日间曲线 / Severe clipping must immediately restore daylight AE."""

    class Constraint:
        Normal = "constraint-normal"
        Shadows = "constraint-shadows"

    class Metering:
        Matrix = "metering-matrix"

    class Exposure:
        Normal = "exposure-normal"
        Long = "exposure-long"

    class Namespace:
        AeConstraintModeEnum = Constraint
        AeMeteringModeEnum = Metering
        AeExposureModeEnum = Exposure

    class FakeCamera:
        camera_controls = {
            "AeConstraintMode": object(),
            "AeMeteringMode": object(),
            "AeExposureMode": object(),
            "ExposureValue": object(),
            "FrameDurationLimits": object(),
        }

        def __init__(self) -> None:
            self.controls: list[dict[str, Any]] = []

        def set_controls(self, controls: dict[str, Any]) -> None:
            self.controls.append(controls)

    camera = _camera(ae_exposure_value=1.0)
    fake = FakeCamera()
    camera.camera = fake
    camera._ae_scene_mode = "starfield"
    camera._ae_effective_exposure_value = 1.5
    monkeypatch.setattr(
        camera, "_load_ae_control_namespace", lambda: (Namespace, "test")
    )

    camera._update_aggressive_auto_exposure(
        {
            "p50": 220.0,
            "p90": 250.0,
            "p99": 255.0,
            "p99_8": 255.0,
            "saturated_fraction": 0.25,
        }
    )

    scene_update = next(item for item in fake.controls if "AeExposureMode" in item)
    assert camera._ae_scene_mode == "daylight"
    assert scene_update["AeExposureMode"] == "exposure-long"
    assert scene_update["AeConstraintMode"] == "constraint-normal"
    assert camera._ae_effective_exposure_value == pytest.approx(0.0)


@pytest.mark.unit
def test_product_tuning_loader_reports_bundled_source() -> None:
    """产品 tuning 成功时记录可诊断来源 / Report the bundled source after a successful load."""

    class FakePicamera2:
        @staticmethod
        def load_tuning_file(name: str, *, dir: str) -> dict[str, str]:
            assert name == "imx327.json"
            assert dir.endswith("hardware/tuning")
            return {"loaded": name}

    camera = _camera()
    tuning = camera._load_picamera_tuning(FakePicamera2)

    assert tuning == {"loaded": "imx327.json"}
    assert camera._tuning_source == "product:imx327.json"
    assert camera._tuning_loaded is True
    assert camera._tuning_error is None


@pytest.mark.unit
def test_tuning_loader_falls_back_without_exposing_override_path(tmp_path) -> None:
    """覆盖文件失败时安全回退且 API 状态不泄露路径 / Fall back without exposing override paths."""

    class MissingTuningPicamera2:
        @staticmethod
        def load_tuning_file(name: str, *, dir: str) -> dict[str, str]:
            raise FileNotFoundError(f"{dir}/{name}")

    secret_path = tmp_path / "private-camera-tuning.json"
    camera = _camera(tuning_file=str(secret_path))

    assert camera._load_picamera_tuning(MissingTuningPicamera2) is None
    assert camera._tuning_source == "system_default"
    assert camera._tuning_loaded is False
    assert camera._tuning_error == "FileNotFoundError"
    assert str(tmp_path) not in camera._tuning_error


@pytest.mark.unit
def test_histogram_stats_use_lores_and_include_highlight_tail() -> None:
    """亮度统计使用有界直方图并保留高光尾部 / Use bounded histograms and retain highlight-tail data."""

    class Request:
        @staticmethod
        def make_array(stream: str) -> np.ndarray:
            assert stream == "lores"
            return np.array([[0, 10, 20, 30], [40, 50, 250, 255]], dtype=np.uint8)

    camera = _camera(lores_width=4, lores_height=2)
    camera._lores_available = True
    camera._collect_lores_stats(Request())

    stats = camera._last_lores_stats
    assert stats["source"] == "lores"
    assert stats["sample_count"] == 8
    assert stats["p50"] == 30.0
    assert stats["p99_8"] == 255.0
    assert stats["saturated_fraction"] == pytest.approx(0.25)


@pytest.mark.unit
def test_histogram_stats_fall_back_to_bounded_main_stream() -> None:
    """无 lores 时仅有界采样主流绿通道 / Sample a bounded main-stream green channel without lores."""
    camera = _camera()
    camera._lores_available = False
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    image[..., 1] = 64

    camera._collect_lores_stats(object(), main_image=image)

    stats = camera._last_lores_stats
    assert stats["source"] == "main_fallback"
    assert stats["sample_count"] <= camera.LUMINANCE_STATS_MAX_SAMPLES
    assert stats["p50"] == 64.0


@pytest.mark.unit
def test_frame_duration_control_reports_primary_and_fallback_paths() -> None:
    """帧周期控制必须明确报告主路径和降级路径 / Report primary and fallback frame-duration paths."""

    class FakeCamera:
        camera_controls = {"FrameDurationLimits": object()}

        def __init__(self) -> None:
            self.fail_limits = False
            self.controls: list[dict[str, Any]] = []

        def set_controls(self, controls: dict[str, Any]) -> None:
            if self.fail_limits and "FrameDurationLimits" in controls:
                raise RuntimeError("unsupported at runtime")
            self.controls.append(controls)

    camera = _camera()
    fake = FakeCamera()
    camera.camera = fake

    camera._apply_frame_duration_controls()
    assert camera._frame_duration_control == "frame_duration_limits"

    fake.fail_limits = True
    camera._apply_frame_duration_controls()
    assert camera._frame_duration_control == "frame_rate_fallback"
    assert fake.controls[-1] == {"FrameRate": 8.0}
    assert camera._frame_duration_control_error == "RuntimeError"
