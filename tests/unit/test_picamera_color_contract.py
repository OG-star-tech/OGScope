"""Picamera2 到 JPEG 的 RGB 色序契约 / RGB byte-order contract from Picamera2 to JPEG."""

from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from ogscope.domain.camera.encoding import OpenCVEncoder
from ogscope.platform.hardware.camera import IMX327MIPICamera


@pytest.mark.unit
def test_picamera_red_pixel_remains_red_in_preview_jpeg():
    camera = IMX327MIPICamera(
        {
            "width": 160,
            "height": 120,
            "rotation": 0,
            "auto_exposure": False,
            "lores_enabled": False,
        }
    )
    camera.camera = SimpleNamespace(create_video_configuration=lambda **kw: kw)
    config = camera._create_video_configuration()
    # 官方 SDK 的格式名称按小端字节序定义，RGB888 数组实际为 BGR。
    # The SDK uses little-endian format names: RGB888 arrays contain BGR bytes.
    pixels = {"RGB888": [0, 0, 255], "BGR888": [255, 0, 0]}
    frame = np.full((120, 160, 3), pixels[config["main"]["format"]], dtype=np.uint8)
    request = SimpleNamespace(
        make_array=lambda _stream: frame,
        get_metadata=lambda: {"ExposureTime": 1000},
        release=lambda: None,
    )
    camera.camera = SimpleNamespace(
        capture_request=lambda **_kw: request,
        wait=lambda job, **_kw: job,
    )
    camera.is_initialized = camera.is_capturing = True
    rgb = camera.get_video_frame()
    assert rgb is not None
    np.testing.assert_array_equal(rgb[60, 80], [255, 0, 0])
    jpeg = OpenCVEncoder().encode_jpeg(rgb, source_format="RGB888")
    assert jpeg is not None
    decoded = cv2.imdecode(np.frombuffer(jpeg.data, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded[60, 80, 2] > 240
    assert decoded[60, 80, 0] < 10
