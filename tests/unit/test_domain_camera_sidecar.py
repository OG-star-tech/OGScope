from __future__ import annotations

import pytest

from ogscope.domain.camera.sidecar import merge_capture_sidecar_into_info


@pytest.mark.unit
def test_merge_capture_sidecar_into_info_flattens_camera_and_extra() -> None:
    info = {"name": "VID_001.avi"}
    capture_info = {
        "camera": {
            "exposure_us": 10000,
            "output_width": 1920,
            "output_height": 1080,
            "sensor": "imx",
        },
        "extra": {"codec": "MJPG"},
    }

    merge_capture_sidecar_into_info(info, capture_info)

    assert info["name"] == "VID_001.avi"
    assert info["exposure_us"] == 10000
    assert info["resolution"] == "1920x1080"
    assert info["sensor"] == "imx"
    assert info["codec"] == "MJPG"


@pytest.mark.unit
def test_merge_capture_sidecar_does_not_override_existing_fields() -> None:
    info = {}
    capture_info = {
        "resolution": "640x480",
        "camera": {"output_width": 1920, "output_height": 1080},
        "extra": {"resolution": "1280x720"},
    }

    merge_capture_sidecar_into_info(info, capture_info)

    assert info["resolution"] == "640x480"
