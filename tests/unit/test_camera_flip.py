"""IMX327 镜像几何单元测试（无相机硬件）/ Mirror geometry unit tests without camera hardware."""

import numpy as np
import pytest

from ogscope.platform.hardware.camera import IMX327MIPICamera


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
