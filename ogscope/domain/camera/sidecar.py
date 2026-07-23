"""
相机侧车信息合并工具 / Camera sidecar merge helpers.
"""

from __future__ import annotations

from typing import Any


def merge_capture_sidecar_into_info(
    info: dict[str, Any],
    capture_info: dict[str, Any],
) -> None:
    """将 camera/extra 字段展开到顶层 / Flatten camera/extra fields to top-level."""
    cam = capture_info.get("camera")
    if isinstance(cam, dict):
        for key in (
            "exposure_us",
            "analogue_gain",
            "digital_gain",
            "fps",
            "auto_exposure",
            "rotation",
            "flip_horizontal",
            "flip_vertical",
            "sampling_mode",
            "color_mode",
            "sensor",
            "resolution",
        ):
            if key not in capture_info and key in cam:
                capture_info[key] = cam[key]
        if capture_info.get("resolution") is None:
            ow = cam.get("output_width") or cam.get("width")
            oh = cam.get("output_height") or cam.get("height")
            if ow and oh:
                capture_info["resolution"] = f"{ow}x{oh}"
    extra = capture_info.get("extra")
    if isinstance(extra, dict):
        for key, value in extra.items():
            if key not in capture_info:
                capture_info[key] = value
    info.update(capture_info)
