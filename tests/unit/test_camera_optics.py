"""产品光学模型测试 / Product optics model tests."""

from __future__ import annotations

import pytest

from ogscope.camera_optics import IMX327_16MM_F14_OPTICS, SC235HAI_16MM_F14_OPTICS


@pytest.mark.unit
def test_imx327_16mm_profile_separates_full_and_effective_fov() -> None:
    """全幅名义视场不能冒充 720p 有效视场 / Full nominal FOV cannot replace 720p effective FOV."""
    optics = IMX327_16MM_F14_OPTICS.describe_capture(
        capture_width_px=1280,
        capture_height_px=720,
        sampling_mode="native",
        rotation_deg=180,
    )

    assert optics["sensor"] == {
        "model": "IMX327",
        "pixel_pitch_um": 2.9,
        "recording_width_px": 1920,
        "recording_height_px": 1080,
    }
    assert optics["lens"] == {
        "focal_length_mm": 16.0,
        "aperture_f_number": 1.4,
        "resolution_rating_mp": 5.0,
        "mount": "M12",
        "ir_cut_filter": True,
    }
    assert optics["full_sensor_fov_deg"]["width"] == pytest.approx(19.74)
    assert optics["full_sensor_fov_deg"]["height"] == pytest.approx(11.18)
    assert optics["theoretical_effective_fov_deg"]["width"] == pytest.approx(13.23)
    assert optics["effective_fov_deg"] == {
        "width": 13.01,
        "height": 7.34,
        "source": "product_calibrated",
    }


@pytest.mark.unit
def test_supersample_uses_full_sensor_region_and_rotation_swaps_axes() -> None:
    """全幅超采样保留视场且旋转交换输出轴 / Supersampling preserves FOV; rotation swaps axes."""
    optics = IMX327_16MM_F14_OPTICS.describe_capture(
        capture_width_px=1280,
        capture_height_px=720,
        sampling_mode="supersample",
        rotation_deg=90,
    )

    assert optics["effective_sensor_region_px"] == {"width": 1920, "height": 1080}
    assert optics["effective_fov_deg"]["width"] == pytest.approx(11.0, abs=0.02)
    assert optics["effective_fov_deg"]["height"] == pytest.approx(19.42, abs=0.02)


@pytest.mark.unit
def test_sc235hai_sees_a_narrower_field_through_the_same_lens() -> None:
    """2.8 µm 像元同镜头视场按像元比例缩小 / 2.8 µm pixels narrow the field by the pitch ratio."""
    imx327 = IMX327_16MM_F14_OPTICS.describe_capture(
        capture_width_px=1280, capture_height_px=720, sampling_mode="native"
    )
    sc235hai = SC235HAI_16MM_F14_OPTICS.describe_capture(
        capture_width_px=1280, capture_height_px=720, sampling_mode="native"
    )

    assert sc235hai["sensor"]["pixel_pitch_um"] == 2.8
    # 标定焦距属于镜头，二者相同 / The calibrated focal length is the lens's, shared
    assert (
        SC235HAI_16MM_F14_OPTICS.calibrated_focal_length_mm
        == IMX327_16MM_F14_OPTICS.calibrated_focal_length_mm
    )
    assert sc235hai["effective_fov_deg"]["width"] == pytest.approx(12.57, abs=0.01)
    assert sc235hai["effective_fov_deg"]["width"] == pytest.approx(
        imx327["effective_fov_deg"]["width"] * 2.8 / 2.9, abs=0.02
    )
