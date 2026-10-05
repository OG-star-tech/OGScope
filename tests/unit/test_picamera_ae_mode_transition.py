"""libcamera 0.5.2 模式切换回归 / libcamera 0.5.2 mode-switch regressions."""

from types import SimpleNamespace

import numpy as np
import pytest

from ogscope.platform.hardware.camera import IMX327MIPICamera


class CoalescingCamera:
    """模拟 SDK 合批与 IPA 自动模式守卫 / Model SDK coalescing and the IPA auto-mode guard."""

    camera_controls = {
        name: object()
        for name in (
            "AeExposureMode",
            "AeConstraintMode",
            "AeMeteringMode",
            "ExposureValue",
            "FrameDurationLimits",
        )
    }
    camera_properties = {}

    def __init__(self):
        self.pending = {}
        self.auto = True
        self.mode = 0

    def set_controls(self, controls):
        self.pending.update(controls)

    def complete_frame(self):
        controls, self.pending = self.pending, {}
        metadata = {}
        # AE 模式预处理先于曝光曲线；字典顺序不能绕过守卫。
        # AE mode preprocessing precedes curve selection; dictionary order cannot bypass the guard.
        if "AeEnable" in controls:
            self.auto = controls["AeEnable"]
            metadata.update(
                ExposureTimeMode=0 if self.auto else 1,
                AnalogueGainMode=0 if self.auto else 1,
            )
        if "AeExposureMode" in controls and not self.auto:
            self.mode = controls["AeExposureMode"]
            metadata["AeExposureMode"] = self.mode
        return metadata


def _camera(monkeypatch):
    camera = IMX327MIPICamera({"width": 160, "height": 120, "auto_exposure": True})
    camera.camera = CoalescingCamera()
    camera.is_initialized = camera.is_capturing = True
    namespace = SimpleNamespace(
        AeExposureModeEnum=SimpleNamespace(Long=2),
        AeConstraintModeEnum=SimpleNamespace(Normal=0, Shadows=2),
        AeMeteringModeEnum=SimpleNamespace(Matrix=2),
    )
    monkeypatch.setattr(
        camera, "_load_ae_control_namespace", lambda: (namespace, "test")
    )
    return camera


@pytest.mark.unit
def test_long_mode_crosses_a_completed_frame_before_enabling_ae(monkeypatch):
    """同帧开启 AE 会失败；分阶段能切到 Long / Same-frame auto fails; staged controls select Long."""
    camera = _camera(monkeypatch)
    backend = camera.camera
    backend.set_controls({"AeEnable": True, "AeExposureMode": 2})
    assert "AeExposureMode" not in backend.complete_frame()
    assert backend.mode == 0

    camera._apply_polar_auto_exposure_controls()
    assert backend.pending["AeEnable"] is False
    assert camera.get_camera_info()["ae_exposure_mode_status"] == "awaiting_metadata"
    camera._advance_ae_mode_transition()
    assert backend.pending["AeEnable"] is False
    camera._record_ae_control_metadata(backend.complete_frame())
    assert backend.mode == 2 and backend.auto is False
    camera._advance_ae_mode_transition()
    assert backend.pending == {"AeEnable": True}
    camera._record_ae_control_metadata(backend.complete_frame())

    info = camera.get_camera_info()
    assert backend.auto is True
    assert info["ae_actual_exposure_mode"] == "long"
    assert info["ae_exposure_mode_status"] == "verified"
    assert info["actual_auto_exposure"] is True
    assert info["actual_auto_gain"] is True

    # 场景切换只变约束和 EV，不再暂停已经生效的 Long 曲线。
    # Scene changes adjust constraints/EV without pausing an acknowledged Long curve.
    camera._ae_scene_mode = "starfield"
    camera._apply_polar_auto_exposure_controls()
    assert backend.pending["AeEnable"] is True
    assert "AeExposureMode" not in backend.pending
    camera._ae_scene_mode = "daylight"
    camera._apply_polar_auto_exposure_controls()
    assert backend.pending["AeConstraintMode"] == 0
    assert backend.pending["AeEnable"] is True


@pytest.mark.unit
def test_mode_acknowledgement_is_not_lost_when_preview_skips_frames(monkeypatch):
    """控制回报所在帧可被预览跳过 / Acknowledgements may occur in frames skipped by preview."""
    camera = _camera(monkeypatch)
    camera._apply_polar_auto_exposure_controls()
    metadata = camera.camera.complete_frame()
    camera._observe_ae_request(SimpleNamespace(get_metadata=lambda: metadata))
    # 无预览消费者时也必须完成切换，单次分析不能停在临时手动曝光。
    # Complete the switch without preview consumers; one-shot analysis must not stay manual.
    assert camera.camera.pending["AeEnable"] is True
    assert camera.get_camera_info()["ae_exposure_mode_status"] == "verified"
    auto_metadata = camera.camera.complete_frame()
    camera._observe_ae_request(SimpleNamespace(get_metadata=lambda: auto_metadata))
    image = np.zeros((120, 160, 3), dtype=np.uint8)
    request = SimpleNamespace(
        make_array=lambda _stream: image,
        get_metadata=lambda: {"ExposureTime": 20_000},
        release=lambda: None,
    )
    monkeypatch.setattr(
        camera.camera, "capture_request", lambda **kw: request, raising=False
    )
    monkeypatch.setattr(camera.camera, "wait", lambda job, **kw: job, raising=False)
    assert camera.capture_image() is not None
    assert camera.camera.auto is True
    assert camera.get_camera_info()["ae_actual_exposure_mode"] == "long"


@pytest.mark.unit
@pytest.mark.parametrize("manual", ["auto_off", "exposure", "gain"])
def test_manual_controls_cancel_pending_auto_enable(monkeypatch, manual):
    """用户切到手动后，晚到的回报不能重新开启 AE / Late acknowledgement must not override manual control."""
    camera = _camera(monkeypatch)
    camera._apply_polar_auto_exposure_controls()
    metadata = camera.camera.complete_frame()
    if manual == "auto_off":
        assert camera.set_auto_exposure(False)
    elif manual == "exposure":
        assert camera.set_exposure(200_000)
    else:
        assert camera.set_gain(2.0)
    camera._record_ae_control_metadata(metadata)
    camera._advance_ae_mode_transition()
    camera.camera.complete_frame()
    assert camera.camera.auto is False
    assert not camera._ae_mode_pending


@pytest.mark.unit
def test_missing_mode_metadata_restores_auto_with_explicit_unverified_status(
    monkeypatch,
):
    """模式回报缺失时有界降级，不能假报成功 / Missing metadata gives bounded fallback, never false success."""
    camera = _camera(monkeypatch)
    camera._apply_polar_auto_exposure_controls()
    camera.camera.complete_frame()
    monkeypatch.setattr(
        "ogscope.platform.hardware.camera.time.monotonic",
        lambda: camera._ae_mode_started_at + 9.0,
    )
    camera._advance_ae_mode_transition()
    camera.camera.complete_frame()
    info = camera.get_camera_info()
    assert camera.camera.auto is True
    assert info["ae_actual_exposure_mode"] is None
    assert info["ae_exposure_mode_status"] == "unverified"
    assert info["ae_control_error"] == "exposure_mode_not_confirmed"


@pytest.mark.unit
def test_fresh_ae_session_reconfirms_mode(monkeypatch):
    """重启或重新启用 AE 必须重新确认模式 / Restarted or re-enabled AE must reconfirm the mode."""
    camera = _camera(monkeypatch)
    camera._ae_actual_exposure_mode = "long"
    camera._ae_exposure_mode_status = "verified"
    camera._reset_autonomous_ae_state()
    camera._apply_polar_auto_exposure_controls()
    assert camera.camera.pending["AeEnable"] is False
    assert camera.get_camera_info()["ae_actual_exposure_mode"] is None
    assert camera.get_camera_info()["ae_exposure_mode_status"] == "awaiting_metadata"


@pytest.mark.unit
def test_unsupported_mode_keeps_auto_running_without_claiming_long(monkeypatch):
    """旧后端不支持模式控制时保持 AE 并明确降级 / Keep AE on and report unsupported mode controls."""
    camera = _camera(monkeypatch)
    monkeypatch.setattr(camera.camera, "camera_controls", {"ExposureValue": object()})
    camera._apply_polar_auto_exposure_controls()
    camera.camera.complete_frame()
    assert camera.camera.auto is True
    assert not camera._ae_mode_pending
    assert camera.get_camera_info()["ae_exposure_mode_status"] == "unsupported"
    assert camera.get_camera_info()["ae_actual_exposure_mode"] is None


@pytest.mark.unit
def test_failed_mode_write_does_not_leave_auto_disabled(monkeypatch):
    """模式控件被拒绝时不能滞留在手动阶段 / Rejected mode controls must not leave AE disabled."""
    camera = _camera(monkeypatch)
    original = camera.camera.set_controls

    def reject_mode(controls):
        if "AeExposureMode" in controls:
            raise RuntimeError("unsupported mode")
        original(controls)

    monkeypatch.setattr(camera.camera, "set_controls", reject_mode)
    camera._apply_polar_auto_exposure_controls()
    camera.camera.complete_frame()
    assert camera.camera.auto is True
    assert not camera._ae_mode_pending
    assert camera.get_camera_info()["ae_exposure_mode_status"] == "unverified"
    assert camera.get_camera_info()["ae_control_error"] == "RuntimeError"


@pytest.mark.unit
def test_temporary_manual_frames_are_not_published_to_one_shot_analysis(monkeypatch):
    """模式切换期间不发布手动帧，恢复自动后才可用于分析 / Publish analysis frames only after auto mode resumes."""
    camera = _camera(monkeypatch)
    camera._apply_polar_auto_exposure_controls()
    image = np.zeros((120, 160, 3), dtype=np.uint8)
    request = SimpleNamespace(
        make_array=lambda _stream: image,
        get_metadata=lambda: {"ExposureTime": 1_000},
        release=lambda: None,
    )
    monkeypatch.setattr(
        camera.camera, "capture_request", lambda **kw: request, raising=False
    )
    monkeypatch.setattr(camera.camera, "wait", lambda job, **kw: job, raising=False)
    assert camera.capture_image() is None
    metadata = camera.camera.complete_frame()
    camera._observe_ae_request(SimpleNamespace(get_metadata=lambda: metadata))
    assert camera.capture_image() is None
    metadata = camera.camera.complete_frame()
    camera._observe_ae_request(SimpleNamespace(get_metadata=lambda: metadata))
    assert camera.capture_image() is not None
