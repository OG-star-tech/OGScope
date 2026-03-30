"""
调试相机 API 的第二层最小测试网（无真实硬件依赖）。
"""

import pytest


class FakeCamera:
    def __init__(self):
        self.is_initialized = True
        self.is_capturing = False
        self.width = 640
        self.height = 360
        self.output_width = 640
        self.output_height = 360
        self.capture_width = 1280
        self.capture_height = 720
        self.fps = 5
        self.sampling_mode = "supersample"
        self.rotation = 180
        self.auto_exposure = True
        self.white_balance_mode = "auto"
        self.exposure_us = 10000
        self.analogue_gain = 1.0
        self.digital_gain = 1.0

    def get_camera_info(self):
        return {
            "width": self.width,
            "height": self.height,
            "output_width": self.output_width,
            "output_height": self.output_height,
            "capture_width": self.capture_width,
            "capture_height": self.capture_height,
            "fps": self.fps,
            "sampling_mode": self.sampling_mode,
            "rotation": self.rotation,
            "auto_exposure": self.auto_exposure,
            "white_balance_mode": self.white_balance_mode,
            "exposure_us": self.exposure_us,
            "analogue_gain": self.analogue_gain,
            "digital_gain": self.digital_gain,
        }

    def start_capture(self):
        self.is_capturing = True
        return True

    def stop_capture(self):
        self.is_capturing = False
        return True

    def set_rotation(self, rotation):
        self.rotation = rotation
        return True

    def set_fps(self, fps):
        self.fps = int(fps)
        return True

    def set_sampling_mode(self, mode):
        self.sampling_mode = mode
        return True

    def set_resolution(self, width, height, fps=None):
        self.output_width = int(width)
        self.output_height = int(height)
        self.width = int(width)
        self.height = int(height)
        if fps is not None:
            self.fps = int(fps)
        return True

    def get_image_quality_metrics(self):
        return {"noise_level": 0.1, "exposure_adequacy": 0.9}

    def set_auto_exposure(self, enabled):
        self.auto_exposure = bool(enabled)
        return True

    def set_exposure(self, exposure):
        self.exposure_us = int(exposure)
        return True

    def set_gain(self, analogue, digital=1.0):
        self.analogue_gain = float(analogue)
        self.digital_gain = float(digital)
        return True

    def set_image_enhancement(self, contrast, brightness, saturation, sharpness):
        return True

    def set_noise_reduction(self, level):
        return True

    def set_white_balance(self, mode, gain_r=1.0, gain_b=1.0):
        self.white_balance_mode = mode
        return True

    def set_color_mode(self, color_mode):
        return True

    def set_night_mode(self, enabled):
        return True


@pytest.fixture
def fake_camera_env(monkeypatch, temp_debug_dir):
    from ogscope.web.api.debug import services as debug_services

    camera = FakeCamera()

    def _get_camera_instance():
        return camera

    async def _noop():
        return None

    monkeypatch.setattr(debug_services, "get_camera_instance", _get_camera_instance)
    monkeypatch.setattr(
        debug_services.DebugCameraService,
        "_ensure_preview_grabber",
        staticmethod(_noop),
    )
    monkeypatch.setattr(
        debug_services.DebugCameraService, "_stop_preview_grabber", staticmethod(_noop)
    )
    monkeypatch.setattr(
        debug_services.DebugCameraService,
        "_restart_preview_grabber",
        staticmethod(_noop),
    )
    return camera


@pytest.mark.unit
def test_debug_camera_status_with_fake_camera(client, fake_camera_env):
    response = client.get("/api/debug/camera/status")
    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is True
    assert data["streaming"] is False
    assert "info" in data


@pytest.mark.unit
def test_debug_camera_start_and_stop(client, fake_camera_env):
    start_resp = client.post("/api/debug/camera/start")
    assert start_resp.status_code == 200
    assert start_resp.json()["success"] is True

    stop_resp = client.post("/api/debug/camera/stop")
    assert stop_resp.status_code == 200
    assert stop_resp.json()["success"] is True


@pytest.mark.unit
def test_debug_camera_rotation(client, fake_camera_env):
    response = client.post("/api/debug/camera/rotation/90")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message_key"] == "server.rotationSet"


@pytest.mark.unit
def test_debug_camera_fps_validation(client):
    response = client.post("/api/debug/camera/fps", params={"fps": 0})
    assert response.status_code == 422


@pytest.mark.unit
def test_debug_camera_fps_success(client, fake_camera_env):
    response = client.post("/api/debug/camera/fps", params={"fps": 12})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["info"]["fps"] == 12


@pytest.mark.unit
def test_debug_camera_sampling_mode_success(client, fake_camera_env):
    response = client.post("/api/debug/camera/sampling", params={"mode": "native"})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["info"]["sampling_mode"] == "native"


@pytest.mark.unit
def test_debug_camera_image_quality_success(client, fake_camera_env):
    response = client.get("/api/debug/camera/image-quality")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert "quality" in body
    assert body["quality"]["noise_level"] == 0.1


@pytest.mark.unit
def test_debug_camera_update_settings_success(client, fake_camera_env):
    payload = {
        "exposure": 12000,
        "gain": 1.5,
        "autoExposure": False,
        "digitalGain": 1.2,
        "contrast": 1.1,
        "brightness": 0.1,
        "saturation": 1.0,
        "sharpness": 1.0,
        "noiseReduction": 1,
        "whiteBalanceMode": "auto",
        "whiteBalanceGainR": 1.0,
        "whiteBalanceGainB": 1.0,
        "colorMode": "color",
    }

    response = client.post("/api/debug/camera/settings", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["settings"]["exposure"] == 12000


@pytest.mark.unit
def test_debug_camera_auto_exposure_switch_success(client, fake_camera_env):
    response = client.post("/api/debug/camera/auto-exposure", params={"enabled": False})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["auto_exposure"] is False
    assert fake_camera_env.auto_exposure is False


@pytest.mark.unit
def test_debug_camera_white_balance_switch_success(client, fake_camera_env):
    response = client.post(
        "/api/debug/camera/white-balance",
        params={"mode": "night", "gain_r": 1.0, "gain_b": 1.0},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert fake_camera_env.white_balance_mode == "night"
