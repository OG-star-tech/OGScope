"""OGScope 产品相机光学模型 / OGScope product camera optics model."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CameraOpticsProfile:
    """固定硬件的名义参数与产品标定 / Nominal hardware and product calibration."""

    profile_id: str
    sensor_model: str
    sensor_pixel_pitch_um: float
    sensor_recording_width_px: int
    sensor_recording_height_px: int
    lens_focal_length_mm: float
    lens_aperture_f_number: float
    lens_resolution_rating_mp: float
    lens_mount: str
    ir_cut_filter: bool
    calibrated_focal_length_mm: float

    @staticmethod
    def _axis_fov_deg(
        pixels: int, pixel_pitch_um: float, focal_length_mm: float
    ) -> float:
        sensor_size_mm = max(1, int(pixels)) * float(pixel_pitch_um) / 1000.0
        return math.degrees(2.0 * math.atan(sensor_size_mm / (2.0 * focal_length_mm)))

    def _fov_pair(
        self, width_px: int, height_px: int, *, calibrated: bool
    ) -> tuple[float, float]:
        focal_length_mm = (
            self.calibrated_focal_length_mm if calibrated else self.lens_focal_length_mm
        )
        return (
            self._axis_fov_deg(width_px, self.sensor_pixel_pitch_um, focal_length_mm),
            self._axis_fov_deg(height_px, self.sensor_pixel_pitch_um, focal_length_mm),
        )

    def describe_capture(
        self,
        *,
        capture_width_px: int,
        capture_height_px: int,
        sampling_mode: str,
        rotation_deg: int = 0,
    ) -> dict[str, Any]:
        """描述当前采集模式的真实有效视场 / Describe effective FOV for the capture mode."""
        mode = str(sampling_mode or "native").lower()
        if mode == "supersample":
            region_width_px = self.sensor_recording_width_px
            region_height_px = self.sensor_recording_height_px
        else:
            region_width_px = min(
                self.sensor_recording_width_px, max(1, int(capture_width_px))
            )
            region_height_px = min(
                self.sensor_recording_height_px, max(1, int(capture_height_px))
            )

        full_width_deg, full_height_deg = self._fov_pair(
            self.sensor_recording_width_px,
            self.sensor_recording_height_px,
            calibrated=False,
        )
        theoretical_width_deg, theoretical_height_deg = self._fov_pair(
            region_width_px,
            region_height_px,
            calibrated=False,
        )
        effective_width_deg, effective_height_deg = self._fov_pair(
            region_width_px,
            region_height_px,
            calibrated=True,
        )

        rotation = int(rotation_deg) % 360
        if rotation in {90, 270}:
            effective_width_deg, effective_height_deg = (
                effective_height_deg,
                effective_width_deg,
            )
            theoretical_width_deg, theoretical_height_deg = (
                theoretical_height_deg,
                theoretical_width_deg,
            )

        return {
            "profile_id": self.profile_id,
            "sensor": {
                "model": self.sensor_model,
                "pixel_pitch_um": self.sensor_pixel_pitch_um,
                "recording_width_px": self.sensor_recording_width_px,
                "recording_height_px": self.sensor_recording_height_px,
            },
            "lens": {
                "focal_length_mm": self.lens_focal_length_mm,
                "aperture_f_number": self.lens_aperture_f_number,
                "resolution_rating_mp": self.lens_resolution_rating_mp,
                "mount": self.lens_mount,
                "ir_cut_filter": self.ir_cut_filter,
            },
            "full_sensor_fov_deg": {
                "width": round(full_width_deg, 2),
                "height": round(full_height_deg, 2),
                "source": "nominal_optical_model",
            },
            "effective_sensor_region_px": {
                "width": region_width_px,
                "height": region_height_px,
            },
            "theoretical_effective_fov_deg": {
                "width": round(theoretical_width_deg, 2),
                "height": round(theoretical_height_deg, 2),
            },
            "effective_fov_deg": {
                "width": round(effective_width_deg, 2),
                "height": round(effective_height_deg, 2),
                "source": "product_calibrated",
            },
            "sampling_mode": mode,
            "rotation_deg": rotation,
        }


# 16 mm 是镜头名义焦距；16.277 mm 来自当前 1280x720 星图解算对 13.01°
# 水平视场的产品标定。两者分开保存，避免把名义规格误当作有效成像视场。
# 16 mm is the nominal lens focal length; 16.277 mm is the product calibration
# derived from the solved 13.01° horizontal FOV at 1280x720. Keep both values
# so nominal optics are never confused with the effective capture FOV.
IMX327_16MM_F14_OPTICS = CameraOpticsProfile(
    profile_id="imx327-16mm-f1.4-ircut-v1",
    sensor_model="IMX327",
    sensor_pixel_pitch_um=2.9,
    sensor_recording_width_px=1920,
    sensor_recording_height_px=1080,
    lens_focal_length_mm=16.0,
    lens_aperture_f_number=1.4,
    lens_resolution_rating_mp=5.0,
    lens_mount="M12",
    ir_cut_filter=True,
    calibrated_focal_length_mm=16.277273749463617,
)

# SC230AI 与 IMX327 像元同为 2.9 µm、记录区同为 1920x1080，配同一镜头视场相同；
# 标定焦距沿用 IMX327 的标定值，直到有 SC230AI 自己的星图标定。
# The SC230AI has the IMX327's 2.9 µm pitch and 1920x1080 recording area, so
# with the same lens it sees the same field; it keeps the IMX327's calibrated
# focal length until the SC230AI has its own from solved star fields.
SC230AI_16MM_F14_OPTICS = CameraOpticsProfile(
    profile_id="sc230ai-16mm-f1.4-ircut-v1",
    sensor_model="SC230AI",
    sensor_pixel_pitch_um=2.9,
    sensor_recording_width_px=1920,
    sensor_recording_height_px=1080,
    lens_focal_length_mm=16.0,
    lens_aperture_f_number=1.4,
    lens_resolution_rating_mp=5.0,
    lens_mount="M12",
    ir_cut_filter=True,
    calibrated_focal_length_mm=IMX327_16MM_F14_OPTICS.calibrated_focal_length_mm,
)

DEFAULT_EFFECTIVE_FOV_WIDTH_DEG = 13.01
DEFAULT_EFFECTIVE_FOV_HEIGHT_DEG = 7.34
