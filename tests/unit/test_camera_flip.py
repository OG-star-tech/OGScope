"""IMX327 镜像几何单元测试（无相机硬件）/ Mirror geometry unit tests without camera hardware."""

import sys
import types
from concurrent.futures import TimeoutError as FutureTimeoutError

import numpy as np
import pytest

from ogscope.domain.camera.encoding import OpenCVEncoder, create_preview_encoder
from ogscope.platform.hardware.camera import IMX327MIPICamera
from ogscope.web.camera_shared import CameraManager


def _minimal_config(**extra: object) -> dict:
    base = {
        "width": 1280,
        "height": 720,
        "fps": 5,
        "exposure_us": 10000,
        "analogue_gain": 1.0,
        "rotation": 0,
    }
    base.update(extra)
    return base


@pytest.mark.unit
def test_apply_flip_horizontal_swaps_columns() -> None:
    cam = IMX327MIPICamera(_minimal_config(flip_horizontal=True, flip_vertical=False))
    img = np.arange(12, dtype=np.uint8).reshape(3, 4)
    out = cam._apply_flip(img)
    np.testing.assert_array_equal(out, np.fliplr(img))


@pytest.mark.unit
def test_apply_flip_vertical_swaps_rows() -> None:
    cam = IMX327MIPICamera(_minimal_config(flip_horizontal=False, flip_vertical=True))
    img = np.arange(12, dtype=np.uint8).reshape(3, 4)
    out = cam._apply_flip(img)
    np.testing.assert_array_equal(out, np.flipud(img))


@pytest.mark.unit
def test_apply_flip_both_matches_np_flipud_fliplr() -> None:
    cam = IMX327MIPICamera(_minimal_config(flip_horizontal=True, flip_vertical=True))
    img = np.arange(12, dtype=np.uint8).reshape(3, 4)
    out = cam._apply_flip(img)
    np.testing.assert_array_equal(out, np.flipud(np.fliplr(img)))


@pytest.mark.unit
def test_apply_flip_identity_when_disabled() -> None:
    cam = IMX327MIPICamera(_minimal_config(flip_horizontal=False, flip_vertical=False))
    img = np.arange(12, dtype=np.uint8).reshape(3, 4)
    out = cam._apply_flip(img)
    np.testing.assert_array_equal(out, img)


class _FakePicamera2:
    """记录控制写入的 Picamera2 替身 / Picamera2 test double that records controls."""

    def __init__(self) -> None:
        self.controls_log: list[dict] = []
        self.camera_controls = {}

    def create_video_configuration(self, **kwargs):
        return kwargs

    def configure(self, _config) -> None:
        return None

    def set_controls(self, controls: dict) -> None:
        self.controls_log.append(dict(controls))


class _FakeCompletedRequest:
    """最小完成请求替身 / Minimal completed-request test double."""

    def __init__(self) -> None:
        self.released = False

    def make_array(self, _stream: str) -> np.ndarray:
        return np.zeros((720, 1280, 3), dtype=np.uint8)

    def get_metadata(self) -> dict:
        return {"ExposureTime": 10000}

    def release(self) -> None:
        self.released = True


class _AsyncCapturePicamera:
    """记录异步抓帧和有限等待 / Track asynchronous capture and bounded waits."""

    def __init__(self, *, time_out: bool = False) -> None:
        self.time_out = time_out
        self.capture_calls = 0
        self.wait_timeouts: list[float] = []
        self.job = object()
        self.request = _FakeCompletedRequest()

    def capture_request(self, *, wait: bool):
        assert wait is False
        self.capture_calls += 1
        return self.job

    def wait(self, job, timeout: float):
        assert job is self.job
        self.wait_timeouts.append(timeout)
        if self.time_out:
            raise FutureTimeoutError
        return self.request


@pytest.mark.unit
def test_initialize_auto_white_balance_really_enables_awb(monkeypatch) -> None:
    fake = _FakePicamera2()
    monkeypatch.setitem(
        sys.modules,
        "picamera2",
        types.SimpleNamespace(Picamera2=lambda: fake),
    )

    cam = IMX327MIPICamera(_minimal_config(white_balance_mode="auto"))

    assert cam.initialize() is True
    assert any(item.get("AwbEnable") is True for item in fake.controls_log)


@pytest.mark.unit
def test_initialize_manual_white_balance_sets_colour_gains(monkeypatch) -> None:
    fake = _FakePicamera2()
    monkeypatch.setitem(
        sys.modules,
        "picamera2",
        types.SimpleNamespace(Picamera2=lambda: fake),
    )

    cam = IMX327MIPICamera(
        _minimal_config(
            white_balance_mode="manual",
            white_balance_gain_r=1.4,
            white_balance_gain_b=1.8,
        )
    )

    assert cam.initialize() is True
    assert any(
        item.get("AwbEnable") is False and item.get("ColourGains") == (1.4, 1.8)
        for item in fake.controls_log
    )


@pytest.mark.unit
def test_capture_uses_picamera_job_with_bounded_wait() -> None:
    fake = _AsyncCapturePicamera()
    cam = IMX327MIPICamera(_minimal_config(capture_timeout_sec=3.5))
    cam.camera = fake
    cam.is_initialized = True
    cam.is_capturing = True

    frame = cam.capture_image()

    assert frame is not None
    assert fake.capture_calls == 1
    assert fake.wait_timeouts == [3.5]
    assert fake.request.released is True
    assert cam._pending_capture_job is None


@pytest.mark.unit
def test_capture_timeout_reuses_pending_job_instead_of_queueing_another() -> None:
    fake = _AsyncCapturePicamera(time_out=True)
    cam = IMX327MIPICamera(_minimal_config(capture_timeout_sec=0.5))
    cam.camera = fake
    cam.is_initialized = True
    cam.is_capturing = True

    assert cam.capture_image() is None
    assert fake.capture_calls == 1
    assert cam._pending_capture_job is fake.job

    fake.time_out = False
    assert cam.capture_image() is not None
    assert fake.capture_calls == 1
    assert cam._pending_capture_job is None


@pytest.mark.unit
def test_encode_frame_preserves_rgb_channel_order() -> None:
    cv2 = pytest.importorskip("cv2")
    rgb = np.zeros((8, 8, 3), dtype=np.uint8)
    rgb[..., 0] = 240
    rgb[..., 1] = 30
    rgb[..., 2] = 10

    data = CameraManager.encode_frame(rgb, "jpeg", 95)
    assert data is not None

    decoded_bgr = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    decoded_rgb = cv2.cvtColor(decoded_bgr, cv2.COLOR_BGR2RGB)
    mean_rgb = decoded_rgb.reshape(-1, 3).mean(axis=0)

    assert mean_rgb[0] > mean_rgb[2] * 4


@pytest.mark.unit
def test_preview_encoder_falls_back_to_opencv_when_turbojpeg_missing(
    monkeypatch,
) -> None:
    """TurboJPEG 缺失时必须安全回退 / Missing TurboJPEG must safely fall back."""
    monkeypatch.setitem(sys.modules, "turbojpeg", types.SimpleNamespace())

    encoder = create_preview_encoder("turbojpeg")

    assert isinstance(encoder, OpenCVEncoder)


@pytest.mark.unit
def test_frame_duration_limits_allow_long_auto_exposure() -> None:
    cam = IMX327MIPICamera(
        _minimal_config(fps=8, auto_exposure=True, auto_exposure_max_us=2_000_000)
    )

    assert cam._compute_frame_duration_limits() == (125_000, 2_000_000)


@pytest.mark.unit
def test_frame_duration_limits_follow_manual_exposure() -> None:
    cam = IMX327MIPICamera(
        _minimal_config(fps=8, auto_exposure=False, exposure_us=250_000)
    )

    assert cam._compute_frame_duration_limits() == (250_000, 250_000)


@pytest.mark.unit
def test_unsupported_noise_reduction_control_is_skipped() -> None:
    fake = _FakePicamera2()
    fake.camera_controls = {}
    cam = IMX327MIPICamera(_minimal_config(noise_reduction_mode="high_quality"))
    cam.camera = fake

    cam._apply_noise_reduction_controls()

    assert fake.controls_log == []
